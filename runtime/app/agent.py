"""Agent runner using the official claude-agent-sdk package.

All inference is routed through the Inference Router:
  claude-agent-sdk -> Claude Code CLI -> Anthropic SDK
    -> POST http://inference-router.platform.svc:8080/v1/messages
    -> Router inspects model name -> proxies to correct backend

Multi-turn conversation is maintained via the SDK's session management:
  - Aviary session_id is passed directly as CLI session_id
  - CLI stores conversation history at <workspace>/.claude/projects/...
  - Pod restart with same PVC: resume=<session_id> restores conversation

Session isolation: each claude-agent-sdk subprocess runs inside a bubblewrap
sandbox where only its own workspace directory is visible. Other sessions'
directories don't exist in the mount namespace. See scripts/claude-sandbox.sh.
"""

import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

# Agent config paths (mounted from ConfigMap)
CONFIG_DIR = Path("/agent/config")
WORKSPACE_ROOT = Path("/workspace/sessions")

# Inference Router URL (K8s Service proxied to docker host)
INFERENCE_ROUTER_URL = os.environ.get(
    "INFERENCE_ROUTER_URL",
    "http://inference-router.platform.svc:8080",
)

# Force SDK to use our bwrap wrapper instead of its bundled binary
CLAUDE_CLI_PATH = "/usr/bin/claude"


def _session_workspace(session_id: str) -> Path:
    """Get the isolated workspace directory for a session."""
    return WORKSPACE_ROOT / session_id


def load_agent_config() -> dict:
    """Load agent configuration from mounted ConfigMap."""
    config = {}

    instruction_file = CONFIG_DIR / "instruction.md"
    if instruction_file.exists():
        config["instruction"] = instruction_file.read_text()

    tools_file = CONFIG_DIR / "tools.json"
    if tools_file.exists():
        config["tools"] = json.loads(tools_file.read_text())

    policy_file = CONFIG_DIR / "policy.json"
    if policy_file.exists():
        config["policy"] = json.loads(policy_file.read_text())

    mcp_file = CONFIG_DIR / "mcp-servers.json"
    if mcp_file.exists():
        config["mcp_servers"] = json.loads(mcp_file.read_text())

    return config


def _has_session_history(workspace: Path, session_id: str) -> bool:
    """Check if a CLI session history exists on PVC for resume."""
    projects_dir = workspace / ".claude" / "projects"
    if not projects_dir.exists():
        return False
    # CLI encodes cwd as directory name with slashes replaced by dashes
    for d in projects_dir.iterdir():
        session_file = d / f"{session_id}.jsonl"
        if session_file.exists():
            return True
    return False


def _build_options(agent_config: dict, model_config: dict, workspace: Path, session_id: str) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions with bubblewrap sandbox isolation.

    The `claude` binary in PATH is a wrapper script (installed by Dockerfile)
    that reads SESSION_WORKSPACE env and runs claude-real inside a bwrap
    mount namespace where only this session's directory is visible.

    Uses the Aviary session_id directly as CLI session_id, so both layers
    share the same ID. Resume is enabled when a prior session history exists.
    """
    model = model_config.get("model", "default")
    backend = model_config.get("backend", "claude")
    can_resume = _has_session_history(workspace, session_id)

    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=agent_config.get("instruction"),
        cwd=workspace,
        cli_path=CLAUDE_CLI_PATH,
        permission_mode="bypassPermissions",
        include_partial_messages=False,
        # First message: session_id sets the CLI session ID
        # Subsequent messages: resume loads existing conversation history
        session_id=None if can_resume else session_id,
        resume=session_id if can_resume else None,
        env={
            "ANTHROPIC_BASE_URL": INFERENCE_ROUTER_URL,
            "ANTHROPIC_API_KEY": "routed-via-inference-router",
            "ANTHROPIC_CUSTOM_HEADERS": f"X-Backend: {backend}",
            "SESSION_WORKSPACE": str(workspace),
            # Prevent CLI from calling api.anthropic.com directly for
            # telemetry, error reporting, auto-updates, or feature flags.
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            # Remap all built-in model tiers to the agent's configured model
            # so CLI internal tasks (WebFetch summarization, subagents, etc.)
            # route through inference router instead of api.anthropic.com.
            **{k: model for k in (
                "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                "ANTHROPIC_DEFAULT_OPUS_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
            )},
            # Proxy env vars for egress proxy — must be explicit because SDK
            # env dict replaces (not merges with) the parent environment.
            **{k: os.environ[k] for k in (
                "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "NODE_OPTIONS",
            ) if k in os.environ},
        },
    )

    tools_list = agent_config.get("tools")
    if tools_list:
        opts.allowed_tools = tools_list

    return opts


async def process_message(
    session_id: str,
    content: str,
    model_config: dict | None = None,
    agent_config_from_api: dict | None = None,
) -> AsyncGenerator[dict, None]:
    """Process a user message through claude-agent-sdk.

    Agent config is received from the API server (sourced from DB) on every
    message, ensuring edits to instruction/tools take effect immediately
    without Pod restart. Falls back to ConfigMap if not provided.

    Each session operates in its own workspace directory for isolation.

    Yields SSE-formatted dicts:
      {"type": "chunk", "content": "..."}
      {"type": "tool_use", "name": "...", "input": {...}}
      {"type": "tool_result", "tool_use_id": "...", "content": "..."}
    """
    workspace = _session_workspace(session_id)
    workspace.mkdir(parents=True, exist_ok=True)

    agent_config = agent_config_from_api if agent_config_from_api else load_agent_config()

    mc = model_config or {"backend": "claude", "model": "default"}
    options = _build_options(agent_config, mc, workspace, session_id)

    full_response = ""

    async def _run_with_client(opts: ClaudeAgentOptions) -> AsyncGenerator[dict, None]:
        nonlocal full_response
        async with ClaudeSDKClient(options=opts) as client:
            await client.query(content)
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            full_response += block.text
                            yield {"type": "chunk", "content": block.text}
                        elif isinstance(block, ToolUseBlock):
                            yield {
                                "type": "tool_use",
                                "name": block.name,
                                "input": block.input,
                            }
                        elif isinstance(block, ToolResultBlock):
                            result_text = block.content if isinstance(block.content, str) else json.dumps(block.content)
                            yield {
                                "type": "tool_result",
                                "tool_use_id": block.tool_use_id,
                                "content": result_text,
                            }

                elif isinstance(message, ResultMessage):
                    if message.result and not full_response:
                        full_response = message.result
                        yield {"type": "chunk", "content": message.result}

    try:
        async for chunk in _run_with_client(options):
            yield chunk
    except Exception as e:
        if options.resume is not None:
            logger.warning(
                "Session resume failed (session_id=%s), retrying as new session: %s",
                session_id, e,
            )
            options.resume = None
            full_response = ""
            try:
                async for chunk in _run_with_client(options):
                    yield chunk
            except Exception as retry_err:
                backend = mc.get("backend", "claude")
                model = mc.get("model", "unknown")
                error_msg = f"[{backend}/{model}] Error: {retry_err}"
                yield {"type": "chunk", "content": error_msg}
                return
        else:
            backend = mc.get("backend", "claude")
            model = mc.get("model", "unknown")
            error_msg = f"[{backend}/{model}] Error: {e}"
            yield {"type": "chunk", "content": error_msg}
            return

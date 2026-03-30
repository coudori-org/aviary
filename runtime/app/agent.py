"""Agent runner using the official claude-agent-sdk package.

All inference is routed through the Inference Router (platform namespace):
  claude-agent-sdk -> Claude Code CLI -> Anthropic SDK
    -> POST http://inference-router.platform.svc:8080/v1/messages
    -> Router inspects model name -> proxies to correct backend

Multi-turn conversation is maintained via the SDK's session management:
  - First message: new session, session_id stored to workspace/.session_id
  - Subsequent messages: resume=<sdk_session_id> resumes the session
  - Pod restart with same PVC: session_id recovered from file

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
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from app.history import append_message

# Agent config paths (mounted from ConfigMap)
CONFIG_DIR = Path("/agent/config")
WORKSPACE_ROOT = Path("/workspace/sessions")

# Inference Router URL (K8s Service in platform namespace)
INFERENCE_ROUTER_URL = os.environ.get(
    "INFERENCE_ROUTER_URL",
    "http://inference-router.platform.svc:8080",
)


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


def _load_session_id(workspace: Path) -> str | None:
    """Load the SDK session ID from the session workspace."""
    sid_file = workspace / ".session_id"
    if sid_file.exists():
        sid = sid_file.read_text().strip()
        return sid if sid else None
    return None


def _save_session_id(workspace: Path, session_id: str) -> None:
    """Save the SDK session ID to the session workspace."""
    (workspace / ".session_id").write_text(session_id)


def _clear_session_id(workspace: Path) -> None:
    """Remove a stale SDK session ID (e.g. after cluster restart)."""
    sid_file = workspace / ".session_id"
    if sid_file.exists():
        sid_file.unlink()
        logger.info("Cleared stale session ID file in %s", workspace)


def _build_options(agent_config: dict, model_config: dict, workspace: Path) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions with bubblewrap sandbox isolation.

    The `claude` binary in PATH is a wrapper script (installed by Dockerfile)
    that reads SESSION_WORKSPACE env and runs claude-real inside a bwrap
    mount namespace where only this session's directory is visible.
    """
    model = model_config.get("model", "claude-sonnet-4-20250514")
    existing_session_id = _load_session_id(workspace)

    opts = ClaudeAgentOptions(
        model=model,
        system_prompt=agent_config.get("instruction"),
        cwd=workspace,
        permission_mode="bypassPermissions",
        include_partial_messages=False,
        resume=existing_session_id,
        env={
            "ANTHROPIC_BASE_URL": INFERENCE_ROUTER_URL,
            "ANTHROPIC_API_KEY": "routed-via-inference-router",
            "SESSION_WORKSPACE": str(workspace),
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
    append_message(session_id, "user", content)

    mc = model_config or {"backend": "claude", "model": "claude-sonnet-4-20250514"}
    options = _build_options(agent_config, mc, workspace)

    full_response = ""

    async def _run_query(opts: ClaudeAgentOptions) -> AsyncGenerator[dict, None]:
        nonlocal full_response
        async for message in query(prompt=content, options=opts):
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
                if message.session_id:
                    _save_session_id(workspace, message.session_id)

                if message.result and not full_response:
                    full_response = message.result
                    yield {"type": "chunk", "content": message.result}

    try:
        async for chunk in _run_query(options):
            yield chunk
    except Exception as e:
        if options.resume is not None:
            logger.warning(
                "Session resume failed (session_id=%s), retrying as new session: %s",
                options.resume, e,
            )
            _clear_session_id(workspace)
            options.resume = None
            full_response = ""
            try:
                async for chunk in _run_query(options):
                    yield chunk
            except Exception as retry_err:
                backend = mc.get("backend", "claude")
                model = mc.get("model", "unknown")
                error_msg = f"[{backend}/{model}] Error: {retry_err}"
                yield {"type": "chunk", "content": error_msg}
                append_message(session_id, "assistant", error_msg)
                return
        else:
            backend = mc.get("backend", "claude")
            model = mc.get("model", "unknown")
            error_msg = f"[{backend}/{model}] Error: {e}"
            yield {"type": "chunk", "content": error_msg}
            append_message(session_id, "assistant", error_msg)
            return

    append_message(session_id, "assistant", full_response)

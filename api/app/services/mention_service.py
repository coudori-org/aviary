"""Parse @slug mentions and resolve each to the caller's owned agents.

Returns a list of *full* agent specs — the supervisor / runtime now need
every field required to execute the sub-agent (runtime_endpoint,
model_config, instruction, tools, mcp_servers).
"""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import User
from app.services import agent_service
from aviary_shared.db.models.mcp import McpAgentToolBinding, McpServer, McpTool

_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9-]*[a-z0-9])")

# The key we mount the LiteLLM MCP endpoint under in `mcpServers` on the
# runtime side (see runtime/src/agent.ts). Claude Code prefixes MCP tools as
# `mcp__{mcp_server_key}__{tool_name}` and LiteLLM then prefixes each
# aggregated tool as `{server_alias}__{tool_name}`, so the final name the
# model sees is `mcp__gateway__{server_alias}__{tool_name}`.
_RUNTIME_MCP_SERVER_KEY = "gateway"
_MCP_PREFIX = f"mcp__{_RUNTIME_MCP_SERVER_KEY}__"
_MCP_TOOL_SEPARATOR = "__"


def extract_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(_MENTION_RE.findall(text)))


def build_mcp_config(legacy_mcp_servers: list) -> dict:
    """Flatten the agent's legacy stdio mcp_servers column into the dict shape
    the runtime expects."""
    config: dict = {}
    for srv in legacy_mcp_servers:
        config[srv["name"]] = {"command": srv["command"], "args": srv.get("args", [])}
    return config


async def _bound_mcp_tool_names(db: AsyncSession, agent_id) -> list[str]:
    """Return `mcp__gateway__{server}__{tool}` names for this agent's MCP
    tool bindings — these plug into Claude Code's `allowedTools` so only the
    tools the owner explicitly bound are visible to the model."""
    rows = (
        await db.execute(
            select(McpAgentToolBinding)
            .where(McpAgentToolBinding.agent_id == agent_id)
            .options(
                joinedload(McpAgentToolBinding.tool).joinedload(McpTool.server)
            )
        )
    ).unique().scalars().all()
    names: list[str] = []
    for b in rows:
        tool: McpTool = b.tool
        server: McpServer = tool.server
        names.append(
            f"{_MCP_PREFIX}{server.name}{_MCP_TOOL_SEPARATOR}{tool.name}"
        )
    return names


async def agent_spec(agent, db: AsyncSession) -> dict:
    """Shape a DB Agent row as the on-the-wire `agent_config` payload (minus
    the fields the supervisor injects: user_token, user_external_id,
    credentials, accessible_agents).

    MCP tool bindings are merged into `tools` so Claude Code's allowedTools
    filter keeps each agent restricted to the tools its owner selected —
    LiteLLM's aggregated `/mcp` endpoint returns everything registered, and
    agent-level scoping now lives in the `mcp_agent_tool_bindings` table
    instead of the retired per-agent gateway URL.
    """
    base_tools = list(agent.tools or [])
    mcp_tools = await _bound_mcp_tool_names(db, agent.id)
    merged_tools = list(dict.fromkeys(base_tools + mcp_tools))

    return {
        "agent_id": str(agent.id),
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "runtime_endpoint": agent.runtime_endpoint,
        "model_config": agent.model_config_json,
        "instruction": agent.instruction,
        "tools": merged_tools,
        "mcp_servers": build_mcp_config(agent.mcp_servers),
    }


async def resolve_mentioned_agents(
    db: AsyncSession,
    user: User,
    slugs: list[str],
    exclude_agent_id: str | None = None,
) -> list[dict]:
    """Return full agent specs for mentioned slugs the user owns (and isn't
    the current agent)."""
    result: list[dict] = []
    for slug in slugs:
        agent = await agent_service.get_agent_by_slug(db, slug)
        if agent is None or agent.status != "active":
            continue
        if exclude_agent_id and str(agent.id) == exclude_agent_id:
            continue
        if agent.owner_id != user.id:
            continue
        result.append(await agent_spec(agent, db))
    return result

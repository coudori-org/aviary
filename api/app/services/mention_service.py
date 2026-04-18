"""Parse @slug mentions and resolve each to the caller's owned agents.

Returns a list of *full* agent specs — the supervisor / runtime need every
field required to execute the sub-agent (runtime_endpoint, model_config,
instruction, tools, mcp_servers).
"""

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, User
from aviary_shared.db.models.mcp import McpAgentToolBinding

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
    """Return `mcp__gateway__{server}__{tool}` qualified names for this
    agent's MCP tool bindings."""
    rows = (
        await db.execute(
            select(
                McpAgentToolBinding.server_name, McpAgentToolBinding.tool_name
            )
            .where(McpAgentToolBinding.agent_id == agent_id)
            .order_by(McpAgentToolBinding.server_name, McpAgentToolBinding.tool_name)
        )
    ).all()
    return [
        f"{_MCP_PREFIX}{server_name}{_MCP_TOOL_SEPARATOR}{tool_name}"
        for server_name, tool_name in rows
    ]


async def agent_spec(agent, db: AsyncSession) -> dict:
    """Shape a DB Agent row as the on-the-wire `agent_config` payload (minus
    fields the supervisor injects: user_token, user_external_id, credentials,
    accessible_agents). MCP bindings are merged into ``tools`` so Claude
    Code's allowedTools filter keeps each agent restricted to its owner's
    selection."""
    return _build_spec(agent, await _bound_mcp_tool_names(db, agent.id))


async def resolve_mentioned_agents(
    db: AsyncSession,
    user: User,
    slugs: list[str],
    exclude_agent_id: str | None = None,
) -> list[dict]:
    """Return full agent specs for mentioned slugs the user owns (and isn't
    the current agent). Batched: one SELECT for the agents, one for every
    matched agent's MCP bindings."""
    if not slugs:
        return []

    agents = (await db.execute(
        select(Agent).where(
            Agent.slug.in_(slugs),
            Agent.owner_id == user.id,
            Agent.status == "active",
        )
    )).scalars().all()

    filtered = [
        a for a in agents
        if not (exclude_agent_id and str(a.id) == exclude_agent_id)
    ]
    if not filtered:
        return []

    bindings: dict = defaultdict(list)
    rows = (await db.execute(
        select(
            McpAgentToolBinding.agent_id,
            McpAgentToolBinding.server_name,
            McpAgentToolBinding.tool_name,
        )
        .where(McpAgentToolBinding.agent_id.in_([a.id for a in filtered]))
        .order_by(McpAgentToolBinding.server_name, McpAgentToolBinding.tool_name)
    )).all()
    for agent_id, server_name, tool_name in rows:
        bindings[agent_id].append(
            f"{_MCP_PREFIX}{server_name}{_MCP_TOOL_SEPARATOR}{tool_name}"
        )

    by_slug = {a.slug: a for a in filtered}
    ordered = [by_slug[s] for s in slugs if s in by_slug]
    return [_build_spec(a, bindings[a.id]) for a in ordered]


def _build_spec(agent, mcp_tool_names: list[str]) -> dict:
    merged = list(dict.fromkeys(list(agent.tools or []) + mcp_tool_names))
    return {
        "agent_id": str(agent.id),
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "runtime_endpoint": agent.runtime_endpoint,
        "model_config": agent.model_config_json,
        "instruction": agent.instruction,
        "tools": merged,
        "mcp_servers": build_mcp_config(agent.mcp_servers),
    }

"""Parse @slug mentions and resolve each to the caller's owned agents.

Returns a list of *full* agent specs — the supervisor / runtime now need
every field required to execute the sub-agent (runtime_endpoint,
model_config, instruction, tools, mcp_servers).
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.services import agent_service

_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9-]*[a-z0-9])")


def extract_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(_MENTION_RE.findall(text)))


def build_mcp_config(legacy_mcp_servers: list) -> dict:
    """Flatten the agent's legacy stdio mcp_servers column into the dict shape
    the runtime expects."""
    config: dict = {}
    for srv in legacy_mcp_servers:
        config[srv["name"]] = {"command": srv["command"], "args": srv.get("args", [])}
    return config


def agent_spec(agent) -> dict:
    """Shape a DB Agent row as the on-the-wire `agent_config` payload (minus
    the fields the supervisor injects: user_token, user_external_id,
    credentials, accessible_agents)."""
    return {
        "agent_id": str(agent.id),
        "slug": agent.slug,
        "name": agent.name,
        "description": agent.description,
        "runtime_endpoint": agent.runtime_endpoint,
        "model_config": agent.model_config_json,
        "instruction": agent.instruction,
        "tools": agent.tools,
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
        result.append(agent_spec(agent))
    return result

"""Mention parsing and accessible agent resolution.

Extracts @slug mentions from text (instruction and user messages),
resolves them to agents, and verifies ACL for the calling user.
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.schemas.agent import AccessibleAgent
from app.services import acl_service, agent_service

# Matches @slug where slug follows the agent slug pattern: lowercase alphanumeric + hyphens
_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9-]*[a-z0-9])")


def extract_mentions(text: str) -> list[str]:
    """Extract unique @slug mentions from text."""
    return list(dict.fromkeys(_MENTION_RE.findall(text)))


async def resolve_mentioned_agents(
    db: AsyncSession,
    user: User,
    slugs: list[str],
    exclude_agent_id: str | None = None,
) -> list[AccessibleAgent]:
    """Resolve slug list to AccessibleAgent configs, filtered by ACL.

    Only returns agents that:
    - exist and are active
    - the user has "chat" permission on
    - are not the current agent (exclude_agent_id)
    """
    result: list[AccessibleAgent] = []

    for slug in slugs:
        agent = await agent_service.get_agent_by_slug(db, slug)
        if agent is None or agent.status != "active":
            continue

        if exclude_agent_id and str(agent.id) == exclude_agent_id:
            continue

        role = await acl_service.resolve_agent_role(db, user, agent)
        if not acl_service.has_permission(role, "chat"):
            continue

        result.append(AccessibleAgent(
            slug=agent.slug,
            name=agent.name,
            description=agent.description,
        ))

    return result

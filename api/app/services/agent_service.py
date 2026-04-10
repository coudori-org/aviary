"""Agent business logic: CRUD with ACL checks.

Infrastructure provisioning is fully delegated to the agent supervisor.
"""

import uuid
import logging

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import or_, exists

from app.db.models import Agent, Session, User
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services import acl_service, agent_supervisor

logger = logging.getLogger(__name__)


async def create_agent(db: AsyncSession, user: User, data: AgentCreate) -> Agent:
    """Create a new agent. Infrastructure provisioning is delegated to the supervisor."""
    # Check slug uniqueness
    existing = await db.execute(select(Agent).where(Agent.slug == data.slug))
    if existing.scalar_one_or_none():
        raise ValueError(f"Agent slug '{data.slug}' already exists")

    agent = Agent(
        name=data.name,
        slug=data.slug,
        description=data.description,
        owner_id=user.id,
        instruction=data.instruction,
        model_config_json=data.model_config_data.model_dump(),
        tools=data.tools,
        mcp_servers=[s.model_dump() for s in data.mcp_servers],
        visibility=data.visibility,
        category=data.category,
        icon=data.icon,
    )
    db.add(agent)
    await db.flush()

    # Register with agent supervisor (secure defaults, best-effort)
    try:
        await agent_supervisor.register_agent(
            agent_id=str(agent.id),
            owner_id=str(user.id),
            config={
                "instruction": data.instruction,
                "tools": data.tools,
                "mcp_servers": [s.model_dump() for s in data.mcp_servers],
            },
        )
    except httpx.HTTPError:  # Best-effort: will retry on first message
        logger.warning(
            "Agent supervisor registration failed for agent %s — will retry on first message",
            agent.id, exc_info=True,
        )

    return agent


async def get_agent(
    db: AsyncSession, agent_id: uuid.UUID, include_deleted: bool = False
) -> Agent | None:
    """Get an agent by ID. Set include_deleted=True to also return soft-deleted agents."""
    query = select(Agent).where(Agent.id == agent_id)
    if not include_deleted:
        query = query.where(Agent.status != "deleted")
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_agent_by_slug(db: AsyncSession, slug: str) -> Agent | None:
    """Get an agent by slug."""
    result = await db.execute(select(Agent).where(Agent.slug == slug, Agent.status != "deleted"))
    return result.scalar_one_or_none()


def _agent_visible_filter():
    """Include active agents + deleted agents that still have active sessions."""
    return or_(
        Agent.status != "deleted",
        exists(
            select(Session.id).where(
                Session.agent_id == Agent.id,
                Session.status == "active",
            )
        ),
    )


async def list_agents_for_user(
    db: AsyncSession, user: User, offset: int = 0, limit: int = 50
) -> tuple[list[Agent], int]:
    """List agents visible to a user based on ACL + visibility rules."""
    from app.db.models import AgentACL, TeamMember

    visible = _agent_visible_filter()

    team_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = [row[0] for row in team_ids_result.all()]

    conditions = [
        Agent.owner_id == user.id,
        Agent.visibility == "public",
    ]

    conditions.append(
        exists(
            select(AgentACL.id).where(
                AgentACL.agent_id == Agent.id,
                AgentACL.user_id == user.id,
            )
        )
    )

    if user_team_ids:
        conditions.append(
            exists(
                select(AgentACL.id).where(
                    AgentACL.agent_id == Agent.id,
                    AgentACL.team_id.in_(user_team_ids),
                )
            )
        )
        conditions.append(
            Agent.visibility == "team",
        )

    base_query = select(Agent).where(visible, or_(*conditions))

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_agent(
    db: AsyncSession, agent: Agent, data: AgentUpdate
) -> Agent:
    """Update an agent's configuration. DB only — infrastructure sync is handled by backoffice."""
    if data.name is not None:
        agent.name = data.name
    if data.description is not None:
        agent.description = data.description
    if data.instruction is not None:
        agent.instruction = data.instruction
    if data.model_config_data is not None:
        agent.model_config_json = data.model_config_data.model_dump()
    if data.tools is not None:
        agent.tools = data.tools
    if data.mcp_servers is not None:
        agent.mcp_servers = [s.model_dump() for s in data.mcp_servers]
    if data.visibility is not None:
        agent.visibility = data.visibility
    if data.category is not None:
        agent.category = data.category
    if data.icon is not None:
        agent.icon = data.icon

    await db.flush()
    return agent


async def cleanup_agent_resources(db: AsyncSession, agent: Agent) -> None:
    """Destroy all agent resources and hard-delete from DB.

    Called when a deleted agent has zero remaining sessions, or when an agent
    with no sessions is deleted. Idempotent — safe to call multiple times.
    """
    agent_id_str = str(agent.id)

    # Ask supervisor to remove all agent resources
    try:
        await agent_supervisor.unregister_agent(agent_id_str)
    except httpx.HTTPError:  # Best-effort: cleanup failure is non-critical
        logger.warning("Agent supervisor cleanup failed for agent %s", agent.id, exc_info=True)

    # Hard-delete the agent row since all sessions are gone
    await db.delete(agent)
    await db.flush()


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Delete an agent. If active sessions remain, soft-delete (status=deleted)
    and keep resources alive. Otherwise, clean up everything and hard-delete.

    Deferred cleanup is triggered by session_service.delete_session when the
    last session of a soft-deleted agent is removed.
    """
    from app.services import session_service

    agent.status = "deleted"
    await db.flush()

    remaining = await session_service.count_active_sessions(db, agent.id)
    if remaining == 0:
        await cleanup_agent_resources(db, agent)

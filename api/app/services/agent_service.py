"""Agent CRUD — owner-only."""

import logging
import uuid

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, Session, User
from app.schemas.agent import AgentCreate, AgentUpdate
from app.errors import ConflictError

logger = logging.getLogger(__name__)


async def create_agent(db: AsyncSession, user: User, data: AgentCreate) -> Agent:
    existing = await db.execute(select(Agent).where(Agent.slug == data.slug))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Agent slug '{data.slug}' already exists")

    agent = Agent(
        name=data.name,
        slug=data.slug,
        description=data.description,
        owner_id=user.id,
        instruction=data.instruction,
        model_config_json=data.model_config_json.model_dump(),
        tools=data.tools,
        mcp_servers=[s.model_dump() for s in data.mcp_servers],
        icon=data.icon,
    )
    db.add(agent)
    await db.flush()
    return agent


async def get_agent(
    db: AsyncSession, agent_id: uuid.UUID, include_deleted: bool = False
) -> Agent | None:
    query = select(Agent).where(Agent.id == agent_id)
    if not include_deleted:
        query = query.where(Agent.status != "deleted")
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_agent_by_slug(db: AsyncSession, slug: str) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.slug == slug, Agent.status != "deleted")
    )
    return result.scalar_one_or_none()


def _agent_visible_filter():
    """Active agents + deleted agents that still have active sessions."""
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
    base_query = select(Agent).where(_agent_visible_filter(), Agent.owner_id == user.id)

    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0

    result = await db.execute(
        base_query.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_agent(db: AsyncSession, agent: Agent, data: AgentUpdate) -> Agent:
    if data.name is not None:
        agent.name = data.name
    if data.description is not None:
        agent.description = data.description
    if data.instruction is not None:
        agent.instruction = data.instruction
    if data.model_config_json is not None:
        agent.model_config_json = data.model_config_json.model_dump()
    if data.tools is not None:
        agent.tools = data.tools
    if data.mcp_servers is not None:
        agent.mcp_servers = [s.model_dump() for s in data.mcp_servers]
    if data.icon is not None:
        agent.icon = data.icon

    await db.flush()
    # `updated_at` is server-updated via onupdate=func.now(); refresh so
    # Pydantic from_attributes doesn't lazy-load it after the session
    # commits on the way out.
    await db.refresh(agent)
    return agent


async def cleanup_agent_resources(db: AsyncSession, agent: Agent) -> None:
    await db.delete(agent)
    await db.flush()


async def reap_if_orphaned(db: AsyncSession, agent_id: uuid.UUID) -> None:
    """Hard-delete the agent iff it's soft-deleted and has no active sessions.
    Called from ``session_service.delete_session`` once the session is gone."""
    from app.services import session_service

    agent = await db.get(Agent, agent_id)
    if agent is None or agent.status != "deleted":
        return
    if await session_service.count_active_sessions(db, agent.id) == 0:
        await cleanup_agent_resources(db, agent)


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Soft-delete; hard-delete once every session is gone."""
    from app.services import session_service

    agent.status = "deleted"
    await db.flush()

    remaining = await session_service.count_active_sessions(db, agent.id)
    if remaining == 0:
        await cleanup_agent_resources(db, agent)

"""Agent business logic: CRUD with K8s namespace provisioning and ACL checks."""

import uuid
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, User
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services import acl_service, k8s_service

logger = logging.getLogger(__name__)


async def create_agent(db: AsyncSession, user: User, data: AgentCreate) -> Agent:
    """Create a new agent and provision K8s namespace."""
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
        policy=data.policy.model_dump(),
        visibility=data.visibility,
        category=data.category,
        icon=data.icon,
    )
    db.add(agent)
    await db.flush()

    # Provision K8s namespace
    try:
        ns_name = await k8s_service.create_agent_namespace(
            agent_id=str(agent.id),
            owner_id=str(user.id),
            instruction=data.instruction,
            tools=data.tools,
            policy=data.policy.model_dump(),
            mcp_servers=[s.model_dump() for s in data.mcp_servers],
        )
        agent.namespace = ns_name
    except Exception:
        logger.warning("K8s namespace creation failed for agent %s — continuing without K8s", agent.id, exc_info=True)

    return agent


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    """Get an agent by ID."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.status != "deleted"))
    return result.scalar_one_or_none()


async def get_agent_by_slug(db: AsyncSession, slug: str) -> Agent | None:
    """Get an agent by slug."""
    result = await db.execute(select(Agent).where(Agent.slug == slug, Agent.status != "deleted"))
    return result.scalar_one_or_none()


async def list_agents_for_user(
    db: AsyncSession, user: User, offset: int = 0, limit: int = 50
) -> tuple[list[Agent], int]:
    """List agents visible to a user based on ACL + visibility rules."""
    from app.db.models import AgentACL, TeamMember

    if user.is_platform_admin:
        # Admin sees all non-deleted agents
        count_result = await db.execute(
            select(func.count()).select_from(Agent).where(Agent.status != "deleted")
        )
        total = count_result.scalar() or 0
        result = await db.execute(
            select(Agent)
            .where(Agent.status != "deleted")
            .order_by(Agent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    # Get user's team IDs
    team_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = [row[0] for row in team_ids_result.all()]

    # Build OR conditions for visibility
    # 1. User owns the agent
    # 2. Direct ACL entry for user
    # 3. Team ACL entry for user's teams
    # 4. Public agents
    # 5. Team visibility + shared team with owner
    from sqlalchemy import or_, exists

    conditions = [
        Agent.owner_id == user.id,
        Agent.visibility == "public",
    ]

    # Direct user ACL
    conditions.append(
        exists(
            select(AgentACL.id).where(
                AgentACL.agent_id == Agent.id,
                AgentACL.user_id == user.id,
            )
        )
    )

    if user_team_ids:
        # Team ACL
        conditions.append(
            exists(
                select(AgentACL.id).where(
                    AgentACL.agent_id == Agent.id,
                    AgentACL.team_id.in_(user_team_ids),
                )
            )
        )
        # Team visibility — agent owner shares a team with user
        conditions.append(
            Agent.visibility == "team",
        )

    base_query = select(Agent).where(Agent.status != "deleted", or_(*conditions))

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
    """Update an agent's configuration and sync to K8s."""
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
    if data.policy is not None:
        agent.policy = data.policy.model_dump()
    if data.visibility is not None:
        agent.visibility = data.visibility
    if data.category is not None:
        agent.category = data.category
    if data.icon is not None:
        agent.icon = data.icon

    await db.flush()

    # Sync ConfigMap to K8s
    if agent.namespace:
        try:
            await k8s_service.update_agent_config(
                namespace=agent.namespace,
                instruction=agent.instruction,
                tools=agent.tools,
                policy=agent.policy,
                mcp_servers=agent.mcp_servers,
            )
        except Exception:
            logger.warning("K8s config update failed for agent %s", agent.id, exc_info=True)

    return agent


async def deploy_agent(db: AsyncSession, agent: Agent) -> int:
    """Apply config changes to running sessions by restarting their Pods.

    Pods are deleted and will be re-created on the next message with fresh
    ConfigMap. The SDK session (conversation history) is preserved via PVC,
    and the new system_prompt from the updated ConfigMap is applied on resume.
    Returns the number of sessions restarted.
    """
    from app.db.models import Session

    result = await db.execute(
        select(Session).where(
            Session.agent_id == agent.id,
            Session.status == "active",
            Session.pod_name.is_not(None),
        )
    )
    sessions = result.scalars().all()

    restarted = 0
    for session in sessions:
        if agent.namespace and session.pod_name:
            try:
                await k8s_service._k8s_apply(
                    "DELETE",
                    f"/api/v1/namespaces/{agent.namespace}/pods/{session.pod_name}",
                )
            except Exception:
                logger.warning("Failed to delete pod %s for deploy", session.pod_name, exc_info=True)

            session.pod_name = None
            restarted += 1

    if restarted:
        await db.flush()
        from app.services import redis_service
        for session in sessions:
            await redis_service.cache_session_pod(str(session.id), None, None)

    logger.info("Deployed agent %s: restarted %d sessions", agent.id, restarted)
    return restarted


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Soft-delete an agent and clean up K8s resources."""
    agent.status = "deleted"
    await db.flush()

    if agent.namespace:
        try:
            await k8s_service.delete_agent_namespace(str(agent.id))
        except Exception:
            logger.warning("K8s namespace deletion failed for agent %s", agent.id, exc_info=True)

"""Agent business logic: CRUD with K8s namespace provisioning and ACL checks."""

import uuid
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, User
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services import acl_service, deployment_service, k8s_service

logger = logging.getLogger(__name__)


async def create_agent(db: AsyncSession, user: User, data: AgentCreate) -> Agent:
    """Create a new agent and provision K8s namespace."""
    # Check slug uniqueness
    existing = await db.execute(select(Agent).where(Agent.slug == data.slug))
    if existing.scalar_one_or_none():
        raise ValueError(f"Agent slug '{data.slug}' already exists")

    policy_dict = data.policy.model_dump()
    pod_strategy = policy_dict.get("podStrategy", "lazy")
    min_pods = policy_dict.get("minPods", 1)
    max_pods = policy_dict.get("maxPods", 3)

    agent = Agent(
        name=data.name,
        slug=data.slug,
        description=data.description,
        owner_id=user.id,
        instruction=data.instruction,
        model_config_json=data.model_config_data.model_dump(),
        tools=data.tools,
        mcp_servers=[s.model_dump() for s in data.mcp_servers],
        policy=policy_dict,
        visibility=data.visibility,
        category=data.category,
        icon=data.icon,
        pod_strategy=pod_strategy,
        min_pods=min_pods,
        max_pods=max_pods,
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
            policy=policy_dict,
            mcp_servers=[s.model_dump() for s in data.mcp_servers],
        )
        agent.namespace = ns_name
    except Exception:
        logger.warning("K8s namespace creation failed for agent %s — continuing without K8s", agent.id, exc_info=True)

    # Eager strategy: spawn deployment immediately after namespace creation
    if pod_strategy == "eager" and agent.namespace:
        try:
            await deployment_service.ensure_agent_deployment(db, agent)
        except Exception:
            logger.warning("Eager deployment failed for agent %s — will retry on first message", agent.id, exc_info=True)

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


async def deploy_agent(db: AsyncSession, agent: Agent) -> None:
    """Apply config changes by triggering a rolling restart of the agent Deployment.

    The SDK session (conversation history) is preserved via PVC,
    and the new config is applied on resume since it's passed in the request body.
    """
    if agent.deployment_active:
        try:
            await deployment_service.rolling_restart(agent)
        except Exception:
            logger.warning("Rolling restart failed for agent %s", agent.id, exc_info=True)
    logger.info("Deployed agent %s: triggered rolling restart", agent.id)


async def activate_agent(db: AsyncSession, agent: Agent) -> None:
    """Manually activate an agent's Deployment (for manual pod strategy)."""
    if not agent.namespace:
        raise RuntimeError(f"Agent {agent.id} has no K8s namespace")
    await deployment_service.ensure_agent_deployment(db, agent)


async def deactivate_agent(db: AsyncSession, agent: Agent) -> None:
    """Manually deactivate an agent's Deployment (scale to 0)."""
    await deployment_service.scale_to_zero(db, agent)


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Soft-delete an agent and clean up K8s resources."""
    agent.status = "deleted"
    await db.flush()

    # Delete deployment resources first
    if agent.deployment_active:
        try:
            await deployment_service.delete_agent_deployment(agent)
        except Exception:
            logger.warning("Deployment deletion failed for agent %s", agent.id, exc_info=True)

    # Delete the entire namespace (cascades all remaining resources)
    if agent.namespace:
        try:
            await k8s_service.delete_agent_namespace(str(agent.id))
        except Exception:
            logger.warning("K8s namespace deletion failed for agent %s", agent.id, exc_info=True)

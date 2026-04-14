"""Agent lifecycle ops shared by the JSON API and HTML pages."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aviary_shared.db.models import Agent, Session as SessionModel

from app.services import supervisor_client

logger = logging.getLogger(__name__)


async def activate(agent: Agent) -> None:
    policy = agent.policy
    policy_rules = policy.policy_rules if policy else {}
    min_pods = policy.min_pods if policy else 0
    max_pods = policy.max_pods if policy else 3
    image = policy_rules.get("containerImage") if policy_rules else None
    cpu_limit = policy_rules.get("maxCpuPerSession") if policy_rules else None
    memory_limit = policy_rules.get("maxMemoryPerSession") if policy_rules else None

    sa = agent.service_account
    await supervisor_client.ensure_agent(
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        image=image,
        sa_name=sa.name,
        min_pods=min_pods,
        max_pods=max_pods,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
    )
    await _sync_identity(agent)


async def _sync_identity(agent: Agent) -> None:
    """Bind egress identity based on the agent's ServiceAccount sg_refs."""
    sa = agent.service_account
    sg_refs = list(sa.sg_refs) if sa and sa.sg_refs else []
    try:
        if sg_refs:
            await supervisor_client.bind_identity(
                str(agent.id), sg_refs, sa_name=sa.name,
            )
        else:
            await supervisor_client.unbind_identity(str(agent.id))
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning("Identity sync failed for agent %s", agent.id, exc_info=True)
    except httpx.HTTPError:
        logger.warning("Identity sync failed for agent %s", agent.id, exc_info=True)


async def deactivate(agent: Agent) -> None:
    await supervisor_client.scale_to_zero(str(agent.id))


async def rolling_restart(agent: Agent) -> None:
    await supervisor_client.rolling_restart(str(agent.id))


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Tear down K8s resources then drop the agent from DB. 404s ignored."""
    try:
        await supervisor_client.delete_agent(str(agent.id))
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise

    await db.execute(delete(SessionModel).where(SessionModel.agent_id == agent.id))
    await db.delete(agent)
    await db.flush()


async def find_agent_or_none(db: AsyncSession, agent_id) -> Agent | None:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id).options(
            selectinload(Agent.policy), selectinload(Agent.service_account),
        )
    )
    return result.scalar_one_or_none()


async def sync_identity(agent: Agent) -> None:
    """Public helper for policy routers — bind or unbind identity after DB update."""
    await _sync_identity(agent)

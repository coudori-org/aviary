"""Agent lifecycle ops shared by the JSON API and HTML pages."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent, Session as SessionModel
from aviary_shared.naming import agent_namespace

from app.services import supervisor_client

logger = logging.getLogger(__name__)


async def activate(agent: Agent) -> None:
    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.create_namespace(
            agent_id=str(agent.id), owner_id=str(agent.owner_id),
            policy=agent.policy or {},
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 409:
            raise

    await supervisor_client.ensure_deployment(
        namespace=ns,
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        policy=agent.policy or {},
        min_pods=agent.min_pods,
        max_pods=agent.max_pods,
    )


async def deactivate(agent: Agent) -> None:
    await supervisor_client.scale_to_zero(agent_namespace(str(agent.id)))


async def rolling_restart(agent: Agent) -> None:
    await supervisor_client.rolling_restart(agent_namespace(str(agent.id)))


async def delete_agent(db: AsyncSession, agent: Agent) -> None:
    """Tear down K8s resources then drop the agent from DB. 404s ignored."""
    ns = agent_namespace(str(agent.id))
    for cleanup in (
        lambda: supervisor_client.delete_deployment(ns),
        lambda: supervisor_client.delete_namespace(str(agent.id)),
    ):
        try:
            await cleanup()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise

    await db.execute(delete(SessionModel).where(SessionModel.agent_id == agent.id))
    await db.delete(agent)
    await db.flush()


async def find_agent_or_none(db: AsyncSession, agent_id) -> Agent | None:
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()

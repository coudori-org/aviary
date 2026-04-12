"""Policy management — egress rules, resource limits, pod strategy."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aviary_shared.db.models import Agent, Policy
from aviary_shared.naming import agent_namespace
from app.db import get_db
from app.services import supervisor_client

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_policy_for_agent(db: AsyncSession, agent_id: uuid.UUID) -> tuple[Agent, Policy]:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.policy:
        policy = Policy()
        db.add(policy)
        await db.flush()
        agent.policy_id = policy.id
        await db.flush()
        agent.policy = policy
    return agent, agent.policy


@router.get("/{agent_id}/policy")
async def get_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent, policy = await _get_policy_for_agent(db, agent_id)

    return {
        "agent_id": str(agent.id),
        "policy": policy.policy_rules,
        "pod_strategy": policy.pod_strategy,
        "min_pods": policy.min_pods,
        "max_pods": policy.max_pods,
    }


class PolicyUpdateRequest(BaseModel):
    policy: dict | None = None
    pod_strategy: str | None = None
    min_pods: int | None = None
    max_pods: int | None = None


@router.put("/{agent_id}/policy")
async def update_policy(
    agent_id: uuid.UUID,
    body: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    agent, policy = await _get_policy_for_agent(db, agent_id)

    if body.policy is not None:
        policy.policy_rules = body.policy
    if body.pod_strategy is not None:
        policy.pod_strategy = body.pod_strategy
    if body.min_pods is not None:
        policy.min_pods = body.min_pods
    if body.max_pods is not None:
        policy.max_pods = body.max_pods

    await db.flush()

    ns = agent_namespace(str(agent.id))
    network_policy_synced = True
    sync_error: str | None = None
    try:
        await supervisor_client.update_network_policy(ns, policy.policy_rules)
    except httpx.HTTPStatusError as e:
        network_policy_synced = False
        if e.response.status_code != 404:
            sync_error = str(e)
            logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)
    except httpx.HTTPError as e:
        network_policy_synced = False
        sync_error = str(e)
        logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)

    return {
        "agent_id": str(agent.id),
        "policy": policy.policy_rules,
        "pod_strategy": policy.pod_strategy,
        "min_pods": policy.min_pods,
        "max_pods": policy.max_pods,
        "network_policy_synced": network_policy_synced,
        "sync_error": sync_error,
    }


@router.post("/{agent_id}/policy/sync")
async def force_sync_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent, policy = await _get_policy_for_agent(db, agent_id)

    ns = agent_namespace(str(agent.id))
    synced = True
    try:
        await supervisor_client.update_network_policy(ns, policy.policy_rules)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise HTTPException(status_code=502, detail=f"NetworkPolicy sync failed: {e}") from e
        synced = False
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"NetworkPolicy sync failed: {e}") from e

    return {"agent_id": str(agent.id), "synced": {"network_policy": synced}}

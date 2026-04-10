"""Policy management — egress rules, resource limits, pod strategy."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from aviary_shared.naming import agent_namespace
from app.db import get_db
from app.services import supervisor_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{agent_id}/policy")
async def get_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get current agent policy from DB."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return {
        "agent_id": str(agent.id),
        "policy": agent.policy,
        "pod_strategy": agent.pod_strategy,
        "min_pods": agent.min_pods,
        "max_pods": agent.max_pods,
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
    """Update policy: DB + K8s NetworkPolicy."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.policy is not None:
        agent.policy = body.policy
    if body.pod_strategy is not None:
        agent.pod_strategy = body.pod_strategy
    if body.min_pods is not None:
        agent.min_pods = body.min_pods
    if body.max_pods is not None:
        agent.max_pods = body.max_pods

    await db.flush()

    # Update K8s NetworkPolicy
    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.update_network_policy(ns, agent.policy)
    except httpx.HTTPError:
        logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)

    return {
        "agent_id": str(agent.id),
        "policy": agent.policy,
        "pod_strategy": agent.pod_strategy,
        "min_pods": agent.min_pods,
        "max_pods": agent.max_pods,
    }


@router.post("/{agent_id}/policy/sync")
async def force_sync_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Force re-sync policy to K8s (reconciliation)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    synced = {"network_policy": False}

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.update_network_policy(ns, agent.policy)
        synced["network_policy"] = True
    except httpx.HTTPError:
        logger.warning("NetworkPolicy sync failed for agent %s", agent.id, exc_info=True)

    return {"agent_id": str(agent.id), "synced": synced}

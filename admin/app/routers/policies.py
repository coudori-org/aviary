"""Policy management — egress rules, resource limits, pod strategy."""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from app.db import get_db
from app.services import controller_client, redis_service

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
    """Update policy: DB + Redis egress sync + K8s NetworkPolicy."""
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

    agent_id_str = str(agent.id)

    # Sync egress policy to Redis
    try:
        await redis_service.sync_egress_policy(agent_id_str, agent.policy)
    except Exception:
        logger.warning("Redis egress sync failed for agent %s", agent.id, exc_info=True)

    # Update K8s NetworkPolicy
    ns = f"agent-{agent.id}"
    try:
        await controller_client.update_network_policy(ns, agent.policy)
    except Exception:
        logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)
    try:
        await controller_client.invalidate_egress_cache(agent_id_str)
    except Exception:
        pass

    return {
        "agent_id": agent_id_str,
        "policy": agent.policy,
        "pod_strategy": agent.pod_strategy,
        "min_pods": agent.min_pods,
        "max_pods": agent.max_pods,
    }


@router.post("/{agent_id}/policy/sync")
async def force_sync_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Force re-sync policy to Redis and K8s (reconciliation)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_id_str = str(agent.id)
    synced = {"redis": False, "network_policy": False, "egress_cache": False}

    try:
        await redis_service.sync_egress_policy(agent_id_str, agent.policy)
        synced["redis"] = True
    except Exception:
        logger.warning("Redis sync failed for agent %s", agent.id, exc_info=True)

    ns = f"agent-{agent.id}"
    try:
        await controller_client.update_network_policy(ns, agent.policy)
        synced["network_policy"] = True
    except Exception:
        logger.warning("NetworkPolicy sync failed for agent %s", agent.id, exc_info=True)
    try:
        await controller_client.invalidate_egress_cache(agent_id_str)
        synced["egress_cache"] = True
    except Exception:
        pass

    return {"agent_id": agent_id_str, "synced": synced}

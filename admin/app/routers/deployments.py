"""Deployment management — activate, deactivate, scale, restart, status."""

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


@router.post("/{agent_id}/activate")
async def activate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Create namespace (if needed) + ensure deployment with full policy from DB."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ns = agent_namespace(str(agent.id))

    # Ensure namespace exists
    try:
        await supervisor_client.create_namespace(
            agent_id=str(agent.id), owner_id=str(agent.owner_id),
            policy=agent.policy or {},
        )
    except httpx.HTTPError:  # Best-effort: namespace may already exist
        pass

    # Ensure deployment
    try:
        await supervisor_client.ensure_deployment(
            namespace=ns, agent_id=str(agent.id), owner_id=str(agent.owner_id),
            policy=agent.policy or {},
            min_pods=agent.min_pods, max_pods=agent.max_pods,
        )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Deployment failed: {e}") from e

    return {"status": "activated"}


@router.post("/{agent_id}/deactivate")
async def deactivate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Scale deployment to zero."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.scale_to_zero(ns)
    except httpx.HTTPError:  # Best-effort: scale-down failure is non-critical
        logger.warning("Failed to scale down agent %s", agent.id, exc_info=True)

    return {"status": "deactivated"}


@router.get("/{agent_id}/deployment")
async def get_deployment_status(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get deployment status."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ns = agent_namespace(str(agent.id))
    try:
        status_info = await supervisor_client.get_deployment_status(ns)
    except httpx.HTTPError:  # Best-effort: deployment may not exist
        status_info = {"replicas": 0, "ready_replicas": 0, "updated_replicas": 0}

    return {
        "pod_strategy": agent.pod_strategy,
        "min_pods": agent.min_pods,
        "max_pods": agent.max_pods,
        **status_info,
    }


@router.post("/{agent_id}/deploy")
async def deploy_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Trigger rolling restart to apply config changes."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.rolling_restart(ns)
    except httpx.HTTPError:
        logger.warning("Rolling restart failed for agent %s", agent.id, exc_info=True)

    return {"status": "deploying"}


class ScaleRequest(BaseModel):
    replicas: int
    min_pods: int | None = None
    max_pods: int | None = None


@router.patch("/{agent_id}/scale")
async def scale_agent(
    agent_id: uuid.UUID, body: ScaleRequest, db: AsyncSession = Depends(get_db),
):
    """Manual scaling."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.min_pods is not None:
        agent.min_pods = body.min_pods
    if body.max_pods is not None:
        agent.max_pods = body.max_pods
    await db.flush()

    ns = agent_namespace(str(agent.id))
    try:
        status = await supervisor_client.get_deployment_status(ns)
        if status.get("replicas", 0) > 0 or status.get("ready_replicas", 0) > 0:
            await supervisor_client.scale_deployment(ns, body.replicas, agent.min_pods, agent.max_pods)
    except httpx.HTTPError:
        logger.warning("Scale failed for agent %s", agent.id, exc_info=True)

    return {"status": "scaled", "replicas": body.replicas}

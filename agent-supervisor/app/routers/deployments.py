"""Admin-facing endpoints — agent_id-keyed. Status, scaling, restart, identity binding."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aviary_shared.naming import (
    AGENTS_NAMESPACE,
    RUNTIME_PORT,
    agent_label_selector,
    agent_service_name,
)

from app.backends import get_backend
from app.backends._common.k8s_client import k8s_apply
from app.backends.protocol import AgentSpec, RuntimeBackend
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class EnsureAgentRequest(BaseModel):
    owner_id: str
    image: str | None = None
    sa_name: str = "agent-default-sa"
    min_pods: int = 0
    max_pods: int = 3
    cpu_limit: str | None = None
    memory_limit: str | None = None


@router.post("/agents/{agent_id}/ensure")
async def ensure_agent(
    agent_id: str, body: EnsureAgentRequest,
    backend: RuntimeBackend = Depends(get_backend),
):
    """Create / update Deployment + Service + ScaledObject."""
    spec = AgentSpec(
        agent_id=agent_id,
        owner_id=body.owner_id,
        image=body.image or settings.agent_runtime_image,
        sa_name=body.sa_name,
        min_pods=body.min_pods,
        max_pods=body.max_pods,
        cpu_limit=body.cpu_limit or settings.default_cpu_limit,
        memory_limit=body.memory_limit or settings.default_memory_limit,
    )
    await backend.register_agent(spec)
    return {"ok": True}


@router.delete("/agents/{agent_id}/deployment")
async def delete_agent_deployment(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.unregister_agent(agent_id)
    return {"ok": True}


@router.get("/agents/{agent_id}/status")
async def get_status(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    status = await backend.get_status(agent_id)
    return {
        "exists": status.exists,
        "replicas": status.replicas,
        "ready_replicas": status.ready_replicas,
        "updated_replicas": status.updated_replicas,
    }


class ScaleRequest(BaseModel):
    replicas: int


@router.patch("/agents/{agent_id}/scale")
async def scale_agent(
    agent_id: str, body: ScaleRequest,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.scale(agent_id, body.replicas)
    return {"ok": True, "replicas": body.replicas}


@router.patch("/agents/{agent_id}/scale-to-zero")
async def scale_to_zero(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.scale(agent_id, 0)
    return {"ok": True}


@router.post("/agents/{agent_id}/restart")
async def restart_agent(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.restart(agent_id)
    return {"ok": True}


class IdentityRequest(BaseModel):
    sa_name: str = "agent-default-sa"
    sg_ref: str


@router.put("/agents/{agent_id}/identity")
async def bind_identity(
    agent_id: str, body: IdentityRequest,
    backend: RuntimeBackend = Depends(get_backend),
):
    """Apply egress identity (SA + SG/profile) to the agent."""
    try:
        await backend.identity.ensure_service_account(body.sa_name)
        await backend.identity.bind_identity(agent_id, body.sa_name, body.sg_ref)
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True}


@router.delete("/agents/{agent_id}/identity")
async def unbind_identity(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.identity.unbind_identity(agent_id)
    return {"ok": True}


@router.get("/agents/{agent_id}/metrics")
async def get_agent_metrics(agent_id: str):
    """Aggregate metrics across the agent's pods (for admin UI)."""
    total_active = 0
    total_streaming = 0
    pods_queried = 0

    try:
        pod_list = await k8s_apply(
            "GET",
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/pods?labelSelector={agent_label_selector(agent_id)}",
        )
    except httpx.HTTPError:
        logger.warning("Pod list failed for agent %s", agent_id, exc_info=True)
        return {"total_active": 0, "total_streaming": 0, "pods_queried": 0}

    svc = agent_service_name(agent_id)
    for pod in pod_list.get("items", []):
        pod_name = pod.get("metadata", {}).get("name")
        phase = pod.get("status", {}).get("phase")
        if not pod_name or phase != "Running":
            continue
        try:
            metrics = await k8s_apply(
                "GET",
                f"/api/v1/namespaces/{AGENTS_NAMESPACE}/pods/{pod_name}:{RUNTIME_PORT}/proxy/metrics",
            )
            total_active += metrics.get("sessions_active", 0)
            total_streaming += metrics.get("sessions_streaming", 0)
            pods_queried += 1
        except httpx.HTTPError:
            logger.warning("Metrics fetch failed for pod %s", pod_name, exc_info=True)

    return {
        "total_active": total_active,
        "total_streaming": total_streaming,
        "pods_queried": pods_queried,
    }

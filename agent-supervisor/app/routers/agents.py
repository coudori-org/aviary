"""Agent-centric API used by the API server — translates agent_id to K8s ops."""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from aviary_shared.naming import (
    DEPLOYMENT_NAME,
    PVC_NAME,
    RUNTIME_PORT,
    SERVICE_NAME,
    agent_namespace,
)

from app import provisioning
from app.scaling import touch_activity
from app.k8s import _get_k8s_client, k8s_apply

logger = logging.getLogger(__name__)

router = APIRouter()


class RegisterAgentRequest(BaseModel):
    owner_id: str


@router.post("/agents/{agent_id}/register")
async def register_agent(agent_id: str, body: RegisterAgentRequest):
    """Provision K8s resources with secure defaults (all egress blocked)."""
    await touch_activity(agent_id)
    ns_name = await provisioning.provision_namespace(
        agent_id=agent_id, owner_id=body.owner_id, policy={},
    )
    return {"ok": True, "namespace": ns_name}


@router.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Remove all resources for an agent."""
    ns = agent_namespace(agent_id)

    # k8s_apply treats DELETE 404 as a no-op; other errors propagate.
    for path in [
        f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}",
        f"/api/v1/namespaces/{ns}/services/{SERVICE_NAME}",
        f"/api/v1/namespaces/{ns}/persistentvolumeclaims/{PVC_NAME}",
        f"/api/v1/namespaces/{ns}",
    ]:
        await k8s_apply("DELETE", path)

    logger.info("Unregistered agent %s", agent_id)
    return {"ok": True}


class RunAgentRequest(BaseModel):
    owner_id: str


@router.post("/agents/{agent_id}/run")
async def run_agent(agent_id: str, body: RunAgentRequest):
    """Ensure agent is running. Lazily creates resources with secure defaults if needed."""
    await touch_activity(agent_id)
    ns = agent_namespace(agent_id)
    return await provisioning.ensure_deployment(
        namespace=ns,
        agent_id=agent_id,
        owner_id=body.owner_id,
        policy={},
        min_pods=1,
        max_pods=1,
    )


@router.get("/agents/{agent_id}/ready")
async def check_agent_ready(agent_id: str):
    ns = agent_namespace(agent_id)
    try:
        status = await provisioning.get_deployment_status(ns)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"ready": False, "replicas": 0, "ready_replicas": 0, "updated_replicas": 0}
        raise
    ready = (status.get("ready_replicas") or 0) >= 1
    return {"ready": ready, **status}


@router.get("/agents/{agent_id}/wait")
async def wait_agent_ready(agent_id: str, timeout: int = 90):
    """Block until agent is ready or timeout."""
    ns = agent_namespace(agent_id)
    return await provisioning.wait_for_ready(ns, timeout)


@router.post("/agents/{agent_id}/sessions/{session_id}/message")
async def proxy_session_message(agent_id: str, session_id: str, request: Request):
    """Transparent SSE proxy to agent runtime for a session message."""
    await touch_activity(agent_id)
    ns = agent_namespace(agent_id)
    body = await request.json()
    proxy_path = (
        f"/api/v1/namespaces/{ns}/services/{SERVICE_NAME}:{RUNTIME_PORT}/proxy/message"
    )

    async def generate():
        try:
            async with _get_k8s_client() as client:
                async with client.stream(
                    "POST", proxy_path, json=body, timeout=None
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        logger.error(
                            "Agent stream returned %d: %s", resp.status_code, error_body
                        )
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError:
            logger.exception("SSE proxy error for agent %s", agent_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agents/{agent_id}/sessions/{session_id}/abort")
async def abort_session(agent_id: str, session_id: str):
    """Abort an active session stream."""
    ns = agent_namespace(agent_id)
    proxy_path = (
        f"/api/v1/namespaces/{ns}/services/{SERVICE_NAME}:{RUNTIME_PORT}/proxy/abort/{session_id}"
    )
    try:
        async with _get_k8s_client() as client:
            resp = await client.post(proxy_path, timeout=5)
            return {"ok": True, "status": resp.status_code}
    except httpx.HTTPError:
        logger.warning("Failed to abort session %s for agent %s", session_id, agent_id, exc_info=True)
        return {"ok": False, "reason": "agent_not_reachable"}


@router.delete("/agents/{agent_id}/sessions/{session_id}")
async def cleanup_session(agent_id: str, session_id: str):
    """Clean up session workspace. Best-effort."""
    ns = agent_namespace(agent_id)
    return await provisioning.cleanup_session_workspace(ns, session_id)

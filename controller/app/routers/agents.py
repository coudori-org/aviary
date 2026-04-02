"""Agent-centric API — abstract facade over K8s operations.

Used by the API server which doesn't know about K8s internals.
Translates agent_id/session_id into namespace/deployment operations.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.scaling import touch_activity
from app.k8s import _get_k8s_client, k8s_apply
from app.routers.namespaces import CreateNamespaceRequest, create_namespace
from app.routers.deployments import (
    EnsureDeploymentRequest,
    ensure_deployment,
    get_deployment_status,
    wait_for_ready,
    cleanup_session_workspace,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _namespace(agent_id: str) -> str:
    return f"agent-{agent_id}"


# ── Agent lifecycle ──────────────────────────────────────────


class RegisterAgentRequest(BaseModel):
    owner_id: str
    instruction: str = ""
    tools: list = []
    mcp_servers: list = []


@router.post("/agents/{agent_id}/register")
async def register_agent(agent_id: str, body: RegisterAgentRequest):
    """Register a new agent. Provisions resources with secure defaults (all network blocked)."""
    await touch_activity(agent_id)
    result = await create_namespace(CreateNamespaceRequest(
        agent_id=agent_id,
        owner_id=body.owner_id,
        instruction=body.instruction,
        tools=body.tools,
        policy={},  # Secure defaults
        mcp_servers=body.mcp_servers,
    ))
    return {"ok": True, **result}


@router.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Remove all resources for an agent."""
    ns = _namespace(agent_id)

    # Delete deployment resources first
    for path in [
        f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime",
        f"/api/v1/namespaces/{ns}/services/agent-runtime-svc",
        f"/api/v1/namespaces/{ns}/persistentvolumeclaims/agent-workspace",
    ]:
        try:
            await k8s_apply("DELETE", path)
        except Exception:
            pass

    # Then delete namespace
    try:
        await k8s_apply("DELETE", f"/api/v1/namespaces/{ns}")
    except Exception:
        pass

    logger.info("Unregistered agent %s", agent_id)
    return {"ok": True}


# ── Agent runtime ────────────────────────────────────────────


class RunAgentRequest(BaseModel):
    owner_id: str
    instruction: str = ""
    tools: list = []
    mcp_servers: list = []


@router.post("/agents/{agent_id}/run")
async def run_agent(agent_id: str, body: RunAgentRequest):
    """Ensure agent is running. Lazily creates resources with secure defaults if needed."""
    await touch_activity(agent_id)
    ns = _namespace(agent_id)
    result = await ensure_deployment(ns, EnsureDeploymentRequest(
        agent_id=agent_id,
        owner_id=body.owner_id,
        instruction=body.instruction,
        tools=body.tools,
        policy={},  # Secure defaults
        mcp_servers=body.mcp_servers,
        min_pods=1,
        max_pods=1,
    ))
    return result


@router.get("/agents/{agent_id}/ready")
async def check_agent_ready(agent_id: str):
    """Check if agent has ready instances."""
    ns = _namespace(agent_id)
    status = await get_deployment_status(ns)
    ready = (status.get("ready_replicas") or 0) >= 1
    return {"ready": ready, **status}


@router.get("/agents/{agent_id}/wait")
async def wait_agent_ready(agent_id: str, timeout: int = 90):
    """Block until agent is ready or timeout."""
    ns = _namespace(agent_id)
    return await wait_for_ready(ns, timeout)


# ── Session operations ───────────────────────────────────────


@router.post("/agents/{agent_id}/sessions/{session_id}/message")
async def proxy_session_message(agent_id: str, session_id: str, request: Request):
    """Transparent SSE proxy to agent runtime for a session message."""
    await touch_activity(agent_id)
    ns = _namespace(agent_id)
    body = await request.json()
    proxy_path = (
        f"/api/v1/namespaces/{ns}/services/agent-runtime-svc:3000/proxy/message"
    )

    async def generate():
        try:
            async with _get_k8s_client() as client:
                async with client.stream(
                    "POST", proxy_path, json=body, timeout=300
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        logger.error(
                            "Agent stream returned %d: %s", resp.status_code, error_body
                        )
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except Exception:
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
    ns = _namespace(agent_id)
    proxy_path = (
        f"/api/v1/namespaces/{ns}/services/agent-runtime-svc:3000/proxy/abort/{session_id}"
    )
    try:
        async with _get_k8s_client() as client:
            resp = await client.post(proxy_path, timeout=5)
            return {"ok": True, "status": resp.status_code}
    except Exception:
        logger.warning("Failed to abort session %s for agent %s", session_id, agent_id)
        return {"ok": False, "reason": "agent_not_reachable"}


@router.delete("/agents/{agent_id}/sessions/{session_id}")
async def cleanup_session(agent_id: str, session_id: str):
    """Clean up session workspace. Best-effort."""
    ns = _namespace(agent_id)
    return await cleanup_session_workspace(ns, session_id)

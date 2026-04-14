"""Agent-centric API used by the API server — activator + SSE proxy."""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import redis_client
from app.backends import get_backend
from app.backends._common.k8s_client import new_client
from app.backends.protocol import AgentSpec, RuntimeBackend
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class _OwnerBody(BaseModel):
    owner_id: str


def _default_spec(agent_id: str, owner_id: str) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        owner_id=owner_id,
        image=settings.agent_runtime_image,
        sa_name="agent-default-sa",
        min_pods=settings.default_min_pods,
        max_pods=settings.default_max_pods,
        cpu_limit=settings.default_cpu_limit,
        memory_limit=settings.default_memory_limit,
    )


@router.post("/agents/{agent_id}/register")
async def register_agent(
    agent_id: str, body: _OwnerBody,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.register_agent(_default_spec(agent_id, body.owner_id))
    return {"ok": True}


@router.delete("/agents/{agent_id}")
async def unregister_agent(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.unregister_agent(agent_id)
    return {"ok": True}


@router.post("/agents/{agent_id}/run")
async def run_agent(
    agent_id: str, body: _OwnerBody,
    backend: RuntimeBackend = Depends(get_backend),
):
    """Ensure the agent is running. Lazily registers and activates (0→1)."""
    status = await backend.get_status(agent_id)
    if not status.exists:
        await backend.register_agent(_default_spec(agent_id, body.owner_id))
    await backend.ensure_active(agent_id)
    return {"ok": True}


@router.get("/agents/{agent_id}/ready")
async def check_agent_ready(
    agent_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    status = await backend.get_status(agent_id)
    return {
        "ready": status.ready_replicas >= 1,
        "replicas": status.replicas,
        "ready_replicas": status.ready_replicas,
        "updated_replicas": status.updated_replicas,
    }


@router.get("/agents/{agent_id}/wait")
async def wait_agent_ready(
    agent_id: str, timeout: int = 90,
    backend: RuntimeBackend = Depends(get_backend),
):
    return {"ready": await backend.wait_ready(agent_id, timeout)}


@router.post("/agents/{agent_id}/sessions/{session_id}/message")
async def proxy_session_message(
    agent_id: str, session_id: str, request: Request,
    backend: RuntimeBackend = Depends(get_backend),
):
    """Transparent SSE proxy to the agent runtime."""
    base = await backend.resolve_endpoint(agent_id)
    body = await request.json()

    async def generate():
        try:
            async with new_client() as client:
                async with client.stream(
                    "POST", f"{base}/message", json=body, timeout=None,
                ) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        logger.error("Agent stream %d: %s", resp.status_code, err)
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Agent runtime error ({resp.status_code})'})}\n\n".encode()
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError:
            logger.exception("SSE proxy error for agent %s", agent_id)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Agent runtime connection failed'})}\n\n".encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/agents/{agent_id}/sessions/{session_id}/publish")
async def publish_session_message(
    agent_id: str, session_id: str, request: Request,
    backend: RuntimeBackend = Depends(get_backend),
):
    """Consume runtime SSE and publish each event to Redis.

    Returns a final status summary to the caller — the caller (API server)
    uses this to drive DB persistence and emit the final `done` event.
    The raw event stream stays off the API's path; WS clients receive events
    by subscribing to the session's Redis channel.
    """
    base = await backend.resolve_endpoint(agent_id)
    body = await request.json()

    reached_runtime = False
    error_message: str | None = None

    try:
        async with new_client() as client:
            async with client.stream(
                "POST", f"{base}/message", json=body, timeout=None,
            ) as resp:
                if resp.status_code != 200:
                    err = (await resp.aread()).decode(errors="replace")[:500]
                    logger.error("Runtime stream %d: %s", resp.status_code, err)
                    error_message = f"Agent runtime error ({resp.status_code}): {err}"
                else:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        etype = event.get("type")
                        if etype == "query_started":
                            reached_runtime = True
                            continue
                        if etype == "error":
                            error_message = event.get("message", "Agent runtime error")
                            break
                        await redis_client.append_stream_chunk(session_id, event)
                        await redis_client.publish_message(session_id, event)
    except httpx.HTTPError as e:
        logger.exception("SSE proxy error for agent %s", agent_id)
        error_message = f"Agent runtime connection failed: {e}"

    if error_message:
        await redis_client.set_stream_status(session_id, "error")
        return {"status": "error", "message": error_message, "reached_runtime": reached_runtime}

    await redis_client.set_stream_status(session_id, "complete")
    return {"status": "complete", "reached_runtime": reached_runtime}


@router.post("/agents/{agent_id}/sessions/{session_id}/abort")
async def abort_session(
    agent_id: str, session_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    base = await backend.resolve_endpoint(agent_id)
    try:
        async with new_client() as client:
            resp = await client.post(f"{base}/abort/{session_id}", timeout=5)
            return {"ok": True, "status": resp.status_code}
    except httpx.HTTPError:
        logger.warning("Abort failed for %s/%s", agent_id, session_id, exc_info=True)
        return {"ok": False, "reason": "agent_not_reachable"}


@router.delete("/agents/{agent_id}/sessions/{session_id}")
async def cleanup_session(
    agent_id: str, session_id: str,
    backend: RuntimeBackend = Depends(get_backend),
):
    await backend.workspace.cleanup_session_workspace(agent_id, session_id)
    return {"ok": True}

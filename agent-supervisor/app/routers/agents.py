"""Session-centric API used by the API server and future orchestrators.

The supervisor is stateless: the caller supplies `runtime_endpoint` in the
request body (null → configured default). The supervisor proxies SSE,
publishes each event to Redis, and returns an assembled final message.
"""

from __future__ import annotations

import json
import logging
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import assembly, metrics, redis_client
from app.routing import resolve_runtime_base

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sessions/{session_id}/message")
async def proxy_session_message(session_id: str, request: Request):
    """Transparent SSE passthrough. Used by workflow / A2A sub-agent paths
    that do in-process event transformation rather than going through Redis."""
    body = await request.json()
    base = resolve_runtime_base(body.get("runtime_endpoint"))

    async def generate():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", f"{base}/message", json=body, timeout=None,
                ) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        logger.error("Runtime stream %d: %s", resp.status_code, err)
                        yield (
                            f"data: {json.dumps({'type': 'error', 'message': f'Agent runtime error ({resp.status_code})'})}\n\n"
                        ).encode()
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        except httpx.HTTPError:
            logger.exception("SSE proxy error for session %s", session_id)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': 'Agent runtime connection failed'})}\n\n"
            ).encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/publish")
async def publish_session_message(session_id: str, request: Request):
    """Consume runtime SSE → Redis (for WS broadcast + replay buffer) →
    return the assembled final message to the caller."""
    body = await request.json()
    base = resolve_runtime_base(body.get("runtime_endpoint"))

    reached_runtime = False
    error_message: str | None = None
    started = time.monotonic()

    try:
        async with httpx.AsyncClient() as client:
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
                        metrics.sse_events_total.labels(event_type=etype or "unknown").inc()
                        if etype == "query_started":
                            reached_runtime = True
                            continue
                        if etype == "error":
                            error_message = event.get("message", "Agent runtime error")
                            break
                        await redis_client.append_stream_chunk(session_id, event)
                        await redis_client.publish_message(session_id, event)
    except httpx.HTTPError as e:
        logger.exception("SSE proxy error for session %s", session_id)
        error_message = f"Agent runtime connection failed: {e}"

    publish_duration = time.monotonic() - started
    metrics.publish_duration_seconds.observe(publish_duration)

    if error_message:
        metrics.publish_requests_total.labels(status="error").inc()
        await redis_client.set_stream_status(session_id, "error")
        return {"status": "error", "message": error_message, "reached_runtime": reached_runtime}

    chunks = await redis_client.get_stream_chunks(session_id)
    assembled_text, assembled_blocks = assembly.rebuild_blocks_from_chunks(chunks)
    await assembly.merge_a2a_events(session_id, assembled_blocks)

    await redis_client.set_stream_status(session_id, "complete")
    metrics.publish_requests_total.labels(status="complete").inc()
    return {
        "status": "complete",
        "reached_runtime": reached_runtime,
        "assembled_text": assembled_text,
        "assembled_blocks": assembled_blocks,
    }


class _AbortBody(BaseModel):
    runtime_endpoint: str | None = None
    agent_id: str | None = None


@router.post("/sessions/{session_id}/abort")
async def abort_session(session_id: str, body: _AbortBody):
    base = resolve_runtime_base(body.runtime_endpoint)
    try:
        async with httpx.AsyncClient() as client:
            payload = {"agent_id": body.agent_id} if body.agent_id else {}
            resp = await client.post(
                f"{base}/abort/{session_id}", json=payload, timeout=5,
            )
            return {"ok": True, "status": resp.status_code}
    except httpx.HTTPError:
        logger.warning("Abort failed for session %s", session_id, exc_info=True)
        return {"ok": False, "reason": "runtime_not_reachable"}


class _CleanupBody(BaseModel):
    runtime_endpoint: str | None = None
    agent_id: str


@router.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str, body: _CleanupBody):
    """Tell the runtime to drop its workspace entry for this (agent, session)."""
    base = resolve_runtime_base(body.runtime_endpoint)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{base}/sessions/{session_id}",
                params={"agent_id": body.agent_id},
                timeout=5,
            )
            return {"ok": resp.status_code in (200, 404)}
    except httpx.HTTPError:
        logger.warning("Cleanup failed for session %s", session_id, exc_info=True)
        return {"ok": False}

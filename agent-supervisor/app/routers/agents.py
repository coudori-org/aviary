"""Session-centric supervisor routes.

Endpoints:
  POST   /v1/sessions/{sid}/message  — drive one turn: stream SSE from the
                                       runtime, publish to Redis, assemble,
                                       return the final text + blocks.
  POST   /v1/sessions/{sid}/a2a      — parent runtime's A2A MCP server
                                       streams a sub-agent turn.
  POST   /v1/sessions/{sid}/workspace/tree  — browse session workspace dir.
  POST   /v1/sessions/{sid}/workspace/file  — read a single file's contents.
  POST   /v1/streams/{sid}/abort     — cancel by stream_id (local or fanned
                                       out across replicas).
  DELETE /v1/sessions/{sid}          — ask runtime to drop workspace.
  DELETE /v1/workflows/{root_run_id}/artifacts — drop a run chain's tree.

Auth: Bearer JWT on every route (the supervisor injects
``user_token``/``user_external_id``/``credentials`` server-side on
``/message`` and ``/a2a`` — callers MUST NOT send those fields).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app import metrics, redis_client
from app.auth.dependencies import resolve_identity
from app.routing import resolve_runtime_base
from app.services.identity import enrich_agent_config
from app.services.stream_service import drive_stream

logger = logging.getLogger(__name__)

router = APIRouter()

# stream_id → running task. Abort looks up by stream_id.
_active: dict[str, asyncio.Task] = {}
_DISCONNECT_POLL_SECONDS = 0.5

_abort_listener_task: asyncio.Task | None = None


def _cancel_local(stream_id: str) -> bool:
    task = _active.get(stream_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _run_abort_listener() -> None:
    try:
        async for req in redis_client.iter_abort_requests():
            try:
                sid = req.get("stream_id")
                if sid and _cancel_local(sid):
                    logger.info("Remote abort applied: stream=%s", sid)
            except Exception:  # noqa: BLE001
                logger.exception("abort listener failed to process message")
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("abort listener crashed")


def start_abort_listener() -> None:
    global _abort_listener_task
    if _abort_listener_task is None or _abort_listener_task.done():
        _abort_listener_task = asyncio.create_task(_run_abort_listener())


async def stop_abort_listener() -> None:
    global _abort_listener_task
    task, _abort_listener_task = _abort_listener_task, None
    if task and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _watch_disconnect(request: Request) -> None:
    while True:
        if await request.is_disconnected():
            return
        await asyncio.sleep(_DISCONNECT_POLL_SECONDS)


@router.post("/sessions/{session_id}/message")
async def post_message(session_id: str, request: Request):
    body = await request.json()
    identity = await resolve_identity(request, body)
    await enrich_agent_config(body, identity)

    # `stream_started` is the frontend's signal that the request was
    # accepted — confirmation point for enabling the abort button client-side.
    stream_id = str(uuid.uuid4())
    await redis_client.publish_event(
        session_id,
        {
            "type": "stream_started",
            "stream_id": stream_id,
            "agent_id": body["agent_config"]["agent_id"],
        },
    )

    publish_task = asyncio.create_task(drive_stream(session_id, stream_id, body))
    disconnect_task = asyncio.create_task(_watch_disconnect(request))
    _active[stream_id] = publish_task

    try:
        done, pending = await asyncio.wait(
            [publish_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

        if publish_task in done:
            try:
                return publish_task.result()
            except asyncio.CancelledError:
                await redis_client.set_stream_status(stream_id, "aborted")
                await redis_client.set_session_status(session_id, "idle")
                metrics.publish_requests_total.labels(status="aborted").inc()
                return {"status": "aborted", "stream_id": stream_id, "reached_runtime": False}

        # Caller disconnected before the runtime finished.
        await redis_client.set_stream_status(stream_id, "error")
        await redis_client.set_session_status(session_id, "idle")
        metrics.publish_requests_total.labels(status="disconnected").inc()
        return {"status": "disconnected", "stream_id": stream_id, "reached_runtime": False}
    finally:
        for t in (publish_task, disconnect_task):
            if not t.done():
                t.cancel()
        _active.pop(stream_id, None)


@router.post("/streams/{stream_id}/abort")
async def abort_stream(stream_id: str):
    """Cancel an in-flight stream. Local fast-path when this replica holds
    the task; otherwise fan out via ``supervisor:abort`` so whichever
    replica holds it cancels. Cancelling closes the supervisor→runtime
    TCP, which fires ``res.on('close')`` on the runtime pod."""
    if _cancel_local(stream_id):
        metrics.abort_requests_total.labels(via="local").inc()
        return {"ok": True, "via": "local"}
    await redis_client.publish_abort(stream_id)
    metrics.abort_requests_total.labels(via="broadcast").inc()
    return {"ok": True, "via": "broadcast"}


# ── /a2a — parent runtime's local A2A MCP server → supervisor ───────────────

class _A2ABody(BaseModel):
    parent_session_id: str
    parent_tool_use_id: str
    agent_config: dict
    content_parts: list[dict]


@router.post("/sessions/{session_id}/a2a")
async def a2a_stream(session_id: str, body: _A2ABody, request: Request):
    """Sub-agent stream. SSE forwards to the caller (parent runtime's A2A
    server); ``tool_use`` / ``tool_result`` are also tagged with
    ``parent_tool_use_id`` and stashed in the parent session's Redis
    buffer so the parent's assembly splices them under the right card."""
    sub_agent_config = {**body.agent_config, "is_sub_agent": True}
    sub_agent_config.pop("accessible_agents", None)  # no recursive A2A

    runtime_body: dict = {
        "session_id": body.parent_session_id,
        "agent_config": sub_agent_config,
        "content_parts": body.content_parts,
    }
    identity = await resolve_identity(request, body.model_dump())
    await enrich_agent_config(runtime_body, identity)

    base = resolve_runtime_base(runtime_body["agent_config"].get("runtime_endpoint"))
    parent_tool_use_id = body.parent_tool_use_id

    async def generate():
        started = time.monotonic()
        a2a_status = "complete"
        metrics.active_a2a_streams.inc()
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", f"{base}/message", json=runtime_body, timeout=None,
                ) as resp:
                    if resp.status_code != 200:
                        metrics.runtime_http_errors_total.labels(
                            status_code=str(resp.status_code)
                        ).inc()
                        a2a_status = "error"
                        err = (await resp.aread()).decode(errors="replace")[:500]
                        logger.error("A2A sub-agent stream %d: %s", resp.status_code, err)
                        yield (
                            f"data: {json.dumps({'type': 'error', 'message': f'Sub-agent error ({resp.status_code})'})}\n\n"
                        ).encode()
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        etype = event.get("type")
                        if etype in ("tool_use", "tool_result"):
                            tagged = {**event, "parent_tool_use_id": parent_tool_use_id}
                            await redis_client.publish_event(body.parent_session_id, tagged)
                            await redis_client.append_a2a_event(
                                body.parent_session_id, parent_tool_use_id, tagged,
                            )
                        yield f"data: {json.dumps(event)}\n\n".encode()
        except httpx.HTTPError:
            a2a_status = "error"
            logger.exception("A2A SSE proxy error for session %s", body.parent_session_id)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': 'Sub-agent runtime unreachable'})}\n\n"
            ).encode()
        finally:
            metrics.a2a_duration_seconds.observe(time.monotonic() - started)
            metrics.a2a_requests_total.labels(status=a2a_status).inc()
            metrics.active_a2a_streams.dec()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Cleanup endpoints ───────────────────────────────────────────────────────

class _CleanupBody(BaseModel):
    runtime_endpoint: str | None = None
    agent_id: str


@router.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str, body: _CleanupBody):
    """Ask the runtime to drop its workspace for (session_id, agent_id)."""
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


# ── Workspace browse ────────────────────────────────────────────────────────

class _WorkspaceTreeBody(BaseModel):
    runtime_endpoint: str | None = None
    # Runtime rejects `.claude` / `.venv` paths (per-agent) when this is null.
    agent_id: str | None = None
    path: str = "/"
    include_hidden: bool = False


class _WorkspaceFileBody(BaseModel):
    runtime_endpoint: str | None = None
    agent_id: str | None = None
    path: str


async def _proxy_workspace_get(
    base: str, route: str, params: dict,
) -> tuple[int, dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base}{route}", params=params, timeout=15,
            )
            try:
                payload = resp.json()
            except ValueError:
                payload = {"error": "invalid runtime response"}
            return resp.status_code, payload
    except httpx.HTTPError:
        logger.warning("Workspace proxy failed: %s", route, exc_info=True)
        return 502, {"error": "runtime unreachable"}


@router.post("/sessions/{session_id}/workspace/tree")
async def workspace_tree(
    session_id: str, body: _WorkspaceTreeBody, request: Request,
):
    await resolve_identity(request, body.model_dump())
    base = resolve_runtime_base(body.runtime_endpoint)
    params = {
        "session_id": session_id,
        "path": body.path,
        "include_hidden": "1" if body.include_hidden else "0",
    }
    if body.agent_id:
        params["agent_id"] = body.agent_id
    status_code, payload = await _proxy_workspace_get(
        base, "/workspace/tree", params,
    )
    return JSONResponse(status_code=status_code, content=payload)


@router.post("/sessions/{session_id}/workspace/file")
async def workspace_file(
    session_id: str, body: _WorkspaceFileBody, request: Request,
):
    await resolve_identity(request, body.model_dump())
    base = resolve_runtime_base(body.runtime_endpoint)
    params = {"session_id": session_id, "path": body.path}
    if body.agent_id:
        params["agent_id"] = body.agent_id
    status_code, payload = await _proxy_workspace_get(
        base, "/workspace/file", params,
    )
    return JSONResponse(status_code=status_code, content=payload)


class _WorkflowArtifactsCleanupBody(BaseModel):
    runtime_endpoint: str | None = None


@router.delete("/workflows/{root_run_id}/artifacts")
async def cleanup_workflow_artifacts(
    root_run_id: str, body: _WorkflowArtifactsCleanupBody,
):
    """Drop the entire artifact tree for a workflow run chain. Proxies to
    the runtime because the PVC is only mounted there."""
    base = resolve_runtime_base(body.runtime_endpoint)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{base}/workflows/{root_run_id}/artifacts",
                timeout=10,
            )
            return {"ok": resp.status_code in (200, 404)}
    except httpx.HTTPError:
        logger.warning(
            "Artifact cleanup failed for root_run=%s", root_run_id, exc_info=True,
        )
        return {"ok": False}

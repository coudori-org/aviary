"""Session-centric API.

Endpoints:
  POST /v1/sessions/{sid}/message   — drive one turn: stream SSE from the
                                      runtime, publish events to Redis, assemble
                                      final text + blocks, return them.
  POST /v1/sessions/{sid}/a2a       — parent runtime's A2A MCP server calls
                                      this with the sub-agent's full config.
  POST /v1/streams/{sid}/abort      — cancel an in-flight stream by stream_id.
  DELETE /v1/sessions/{sid}         — ask the runtime to drop its (agent,
                                      session) workspace.

Request body on /message and /a2a:

    {
      "session_id": "...",
      "content_parts": [...],
      "agent_config": {                  # self-contained runtime spec
        "agent_id": "...", "slug": "...", "name": "...", "description": "...",
        "runtime_endpoint": "string | null",
        "model_config": { ... },
        "instruction": "...",
        "tools": [...],
        "mcp_servers": { ... },
        "accessible_agents": [ ...same shape, recursion blocked at the runtime... ]
      }
    }

Auth: `Authorization: Bearer <user JWT>` on both /message and /a2a. The
supervisor injects `agent_config.user_token`, `user_external_id`, and
`credentials` from Vault — callers MUST NOT send those fields.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app import assembly, metrics, redis_client
from app.auth.dependencies import resolve_identity
from app.routing import resolve_runtime_base
from app.services.vault_client import fetch_user_credentials

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


async def _authorise_and_enrich(body: dict, sub: str, user_token: str | None) -> None:
    """Overwrite caller-supplied identity fields with the server-authoritative
    values. Worker callers pass `user_token=None` — we drop the field so the
    runtime / LiteLLM falls back to its master key.
    """
    agent_config = body.get("agent_config") or {}
    if not agent_config.get("agent_id"):
        raise HTTPException(status_code=400, detail="agent_config.agent_id is required")

    agent_config["user_external_id"] = sub
    if user_token:
        agent_config["user_token"] = user_token
    else:
        agent_config.pop("user_token", None)

    credentials = await fetch_user_credentials(sub)
    if credentials:
        agent_config["credentials"] = credentials
    else:
        agent_config.pop("credentials", None)

    body["agent_config"] = agent_config
    # Never forward the worker-auth field to the runtime.
    body.pop("on_behalf_of_sub", None)


# ── /message — the one path API calls ───────────────────────────────────────

async def _drive_stream(
    session_id: str, stream_id: str, body: dict,
) -> dict:
    """Stream runtime SSE → Redis → assembled text/blocks."""
    agent_config = body["agent_config"]
    base = resolve_runtime_base(agent_config.get("runtime_endpoint"))
    reached_runtime = False
    error_message: str | None = None
    aborted = False
    started = time.monotonic()

    await redis_client.set_stream_status(stream_id, "streaming")
    await redis_client.set_session_status(session_id, "streaming")
    await redis_client.set_session_latest_stream(session_id, stream_id)

    metrics.active_streams.inc()
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", f"{base}/message", json=body, timeout=None,
            ) as resp:
                if resp.status_code != 200:
                    metrics.runtime_http_errors_total.labels(
                        status_code=str(resp.status_code)
                    ).inc()
                    err = (await resp.aread()).decode(errors="replace")[:500]
                    logger.error("Runtime stream %d: %s", resp.status_code, err)
                    error_message = f"Agent runtime error ({resp.status_code}): {err}"
                else:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        event["stream_id"] = stream_id
                        etype = event.get("type")
                        metrics.sse_events_total.labels(event_type=etype or "unknown").inc()
                        if etype == "query_started":
                            reached_runtime = True
                            metrics.time_to_query_started_seconds.observe(
                                time.monotonic() - started
                            )
                            continue
                        if etype == "error":
                            # API is the sole publisher of terminal error events
                            # (it owns DB-consistent events). Returning the
                            # message in the response is enough.
                            error_message = event.get("message", "Agent runtime error")
                            break
                        await redis_client.append_stream_chunk(stream_id, event)
                        await redis_client.publish_event(session_id, event)
    except asyncio.CancelledError:
        aborted = True
    except httpx.HTTPError as e:
        logger.exception("SSE proxy error for stream %s", stream_id)
        error_message = f"Agent runtime connection failed: {e}"
    finally:
        metrics.active_streams.dec()

    metrics.publish_duration_seconds.observe(time.monotonic() - started)
    await redis_client.set_session_status(session_id, "idle")

    # Always assemble — abort and error paths both need the partial so the
    # DB stays in sync with Claude Code's JSONL history on the PVC.
    chunks = await redis_client.get_stream_chunks(stream_id)
    assembled_text, assembled_blocks = assembly.rebuild_blocks_from_chunks(chunks)
    await assembly.merge_a2a_events(session_id, assembled_blocks)

    base_return = {
        "stream_id": stream_id,
        "reached_runtime": reached_runtime,
        "assembled_text": assembled_text,
        "assembled_blocks": assembled_blocks,
    }

    if error_message:
        assembled_blocks.append({"type": "error", "message": error_message})
        await redis_client.set_stream_status(stream_id, "error")
        metrics.publish_requests_total.labels(status="error").inc()
        return {"status": "error", "message": error_message, **base_return}

    # Terminal state (done / cancelled) is signalled by the API after it
    # saves the message to the DB — supervisor doesn't know the DB id, so
    # it only sets the stream's Redis status + metrics and returns.
    if aborted:
        await redis_client.set_stream_status(stream_id, "aborted")
        metrics.publish_requests_total.labels(status="aborted").inc()
        return {"status": "aborted", **base_return}

    await redis_client.set_stream_status(stream_id, "complete")
    metrics.publish_requests_total.labels(status="complete").inc()
    return {"status": "complete", **base_return}


@router.post("/sessions/{session_id}/message")
async def post_message(session_id: str, request: Request):
    body = await request.json()
    identity = await resolve_identity(request, body)
    await _authorise_and_enrich(body, identity.sub, identity.user_token)

    # Supervisor owns stream_id allocation. Publishing `stream_started` here
    # is the frontend's signal that the request was accepted — it's the
    # confirmation point for enabling the abort button client-side.
    stream_id = str(uuid.uuid4())
    await redis_client.publish_event(
        session_id,
        {
            "type": "stream_started",
            "stream_id": stream_id,
            "agent_id": body["agent_config"]["agent_id"],
        },
    )

    publish_task = asyncio.create_task(_drive_stream(session_id, stream_id, body))
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


# ── /abort ──────────────────────────────────────────────────────────────────

@router.post("/streams/{stream_id}/abort")
async def abort_stream(stream_id: str):
    """Cancel an in-flight stream. If this replica holds it, fast-path; else
    fan out via `supervisor:abort` so whichever replica holds the task
    cancels it. Cancelling closes the supervisor→runtime TCP connection,
    which fires `req.on('close')` on the runtime pod and aborts the SDK."""
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
    """Sub-agent stream. SSE is forwarded to the caller (parent runtime's A2A
    server), and `tool_use`/`tool_result` are also tagged with
    `parent_tool_use_id` and stashed in the parent session's Redis buffer so
    the parent's assembly splices them under the right tool card."""
    sub_agent_config = {**body.agent_config, "is_sub_agent": True}
    sub_agent_config.pop("accessible_agents", None)  # no recursive A2A

    runtime_body: dict = {
        "session_id": body.parent_session_id,
        "agent_config": sub_agent_config,
        "content_parts": body.content_parts,
    }
    identity = await resolve_identity(request, body.model_dump())
    await _authorise_and_enrich(runtime_body, identity.sub, identity.user_token)

    base = resolve_runtime_base(runtime_body["agent_config"].get("runtime_endpoint"))
    parent_tool_use_id = body.parent_tool_use_id

    from fastapi.responses import StreamingResponse

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


# ── /sessions/{sid} cleanup ─────────────────────────────────────────────────

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


# ── /workflows/{root_run_id}/artifacts cleanup ──────────────────────────────

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

"""Session-centric API used by the API server and future orchestrators.

The supervisor is stateless from the DB's point of view but keeps an
in-memory registry of active publish handlers so that aborts cancel the
right stream. Abort propagation uses HTTP connection closure:

    API cancels httpx → supervisor's outbound stream task cancel →
    httpx client closes TCP → runtime pod's req.on("close") fires → SDK abort.

No direct pod-to-pod routing needed; the Service load-balanced TCP
connection is pod-pinned for its lifetime.

Auth: `/publish` and `/a2a` require an `Authorization: Bearer <user JWT>`
header. The supervisor validates the token via OIDC, extracts the `sub`
claim, and uses it to look up per-user credentials (GitHub token) in
Vault. Those credentials + the validated identity are injected into the
runtime request body — callers MUST NOT pass them in the body.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import assembly, metrics, redis_client
from app.auth.dependencies import extract_bearer_token, get_current_user
from app.auth.oidc import TokenClaims
from app.routing import resolve_runtime_base
from app.services.vault_client import fetch_user_credentials

logger = logging.getLogger(__name__)

router = APIRouter()

# (session_id, agent_id) → running publish task. Used by abort to cancel.
# If the same session+agent publishes again before the previous is cancelled,
# the previous task is cancelled first.
_active: dict[tuple[str, str | None], asyncio.Task] = {}
_DISCONNECT_POLL_SECONDS = 0.5

# Subscriber task that applies remote abort broadcasts to the local registry.
_abort_listener_task: asyncio.Task | None = None


def _registry_key(session_id: str, agent_id: str | None) -> tuple[str, str | None]:
    return (session_id, agent_id)


def _cancel_local(session_id: str, agent_id: str | None) -> bool:
    task = _active.get(_registry_key(session_id, agent_id))
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _run_abort_listener() -> None:
    """Background task: apply remote abort broadcasts to our local registry."""
    try:
        async for req in redis_client.iter_abort_requests():
            try:
                if _cancel_local(req["session_id"], req.get("agent_id")):
                    logger.info(
                        "Remote abort applied: session=%s agent=%s",
                        req["session_id"], req.get("agent_id"),
                    )
            except Exception:  # noqa: BLE001 — single bad msg must not kill the loop
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
    """Return when the client closes its side of the HTTP connection."""
    while True:
        if await request.is_disconnected():
            return
        await asyncio.sleep(_DISCONNECT_POLL_SECONDS)


async def _enrich_agent_config(body: dict, claims: TokenClaims, user_token: str) -> None:
    """Inject validated user identity + Vault-sourced credentials into the
    body's `agent_config` before we forward to the runtime.

    Overwrites any values the caller sent — user_token / user_external_id /
    credentials are supervisor-authoritative.
    """
    agent_config = body.setdefault("agent_config", {})
    agent_config["user_token"] = user_token
    agent_config["user_external_id"] = claims.sub

    credentials = await fetch_user_credentials(claims.sub)
    if credentials:
        agent_config["credentials"] = credentials
    else:
        agent_config.pop("credentials", None)


@router.post("/sessions/{session_id}/message")
async def proxy_session_message(session_id: str, request: Request):
    """Transparent SSE passthrough. Used by workflow / A2A sub-agent paths
    that do in-process event transformation rather than going through Redis.

    This endpoint is unauthenticated — it's an internal entry point for the
    workflow engine, which runs without a user identity. Per-user
    credentials are NOT injected here."""
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


async def _do_publish(
    session_id: str, body: dict,
) -> dict:
    """Stream SSE from runtime, publish each event to Redis, assemble final."""
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

    metrics.publish_duration_seconds.observe(time.monotonic() - started)

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


@router.post("/sessions/{session_id}/publish")
async def publish_session_message(
    session_id: str,
    request: Request,
    claims: TokenClaims = Depends(get_current_user),
):
    """Consume runtime SSE → Redis (for WS broadcast + replay buffer) → return
    the assembled final message to the caller.

    Two ways this handler terminates:
      1. Runtime stream completes → normal response.
      2. Abort: either the caller disconnects (race below) or a sibling
         /abort call cancels our publish task. In both cases the outbound
         httpx stream context exits, which closes the TCP connection to the
         specific runtime pod, which triggers its close-event handler and
         aborts the SDK.
    """
    body = await request.json()
    user_token = extract_bearer_token(request)
    await _enrich_agent_config(body, claims, user_token)

    agent_id = (body.get("agent_config") or {}).get("agent_id")
    key = _registry_key(session_id, agent_id)

    # If another publish is in flight for this session/agent, cancel it first.
    prior = _active.get(key)
    if prior and not prior.done():
        logger.warning("Cancelling in-flight publish for %s/%s", session_id, agent_id)
        prior.cancel()

    publish_task = asyncio.create_task(_do_publish(session_id, body))
    disconnect_task = asyncio.create_task(_watch_disconnect(request))
    _active[key] = publish_task

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
                await redis_client.set_stream_status(session_id, "error")
                metrics.publish_requests_total.labels(status="aborted").inc()
                return {"status": "aborted", "reached_runtime": False}

        # Caller disconnected: publish_task is now cancelled.
        await redis_client.set_stream_status(session_id, "error")
        metrics.publish_requests_total.labels(status="disconnected").inc()
        return {"status": "disconnected", "reached_runtime": False}
    finally:
        # Best-effort cleanup. Whatever is cancelled should settle before we pop.
        for t in (publish_task, disconnect_task):
            if not t.done():
                t.cancel()
        _active.pop(key, None)


class _AbortBody(BaseModel):
    agent_id: str | None = None


@router.post("/sessions/{session_id}/abort")
async def abort_session(session_id: str, body: _AbortBody):
    """Cancel the in-flight publish task for (session_id, agent_id).

    Local fast-path: if this replica holds the task, cancel and return.
    Otherwise fan out via Redis pub/sub so whichever replica holds the
    task can cancel it. Cancelling the task closes the supervisor → runtime
    TCP connection, which fires `req.on('close')` in the runtime pod and
    aborts the SDK query.
    """
    if _cancel_local(session_id, body.agent_id):
        return {"ok": True, "via": "local"}
    await redis_client.publish_abort(session_id, body.agent_id)
    return {"ok": True, "via": "broadcast"}


class _A2ABody(BaseModel):
    """Body for an A2A sub-agent invocation, sent by a parent runtime's
    local A2A MCP server. ACL/auth of the target_agent_id was already
    enforced by the API at chat-start when it built the parent's
    accessible_agents list. The supervisor still authenticates the caller
    via Bearer token so that per-user credentials are injected from Vault
    for the sub-agent runtime too."""

    parent_session_id: str
    parent_tool_use_id: str
    target_agent_id: str
    target_runtime_endpoint: str | None = None
    model_config_data: dict
    agent_config: dict = {}
    content_parts: list[dict]


@router.post("/sessions/{session_id}/a2a")
async def a2a_stream(
    session_id: str,
    body: _A2ABody,
    request: Request,
    claims: TokenClaims = Depends(get_current_user),
):
    """Stream a sub-agent's response.

    SSE is forwarded verbatim to the caller (parent runtime's A2A server).
    `tool_use` / `tool_result` events are also tagged with `parent_tool_use_id`
    and pushed to the parent session's Redis (a2a buffer + pubsub) so the
    parent's assembly + frontend can splice them under the parent tool card.
    """
    base = resolve_runtime_base(body.target_runtime_endpoint)
    parent_tool_use_id = body.parent_tool_use_id

    user_token = extract_bearer_token(request)

    # Sub-agent runtime body. Always strips accessible_agents (no recursive A2A)
    # and marks is_sub_agent so the runtime applies sub-agent prompt framing.
    sub_agent_config = {
        **body.agent_config,
        "agent_id": body.target_agent_id,
        "is_sub_agent": True,
    }
    sub_agent_config.pop("accessible_agents", None)

    runtime_body: dict = {
        "session_id": body.parent_session_id,
        "model_config_data": body.model_config_data,
        "agent_config": sub_agent_config,
        "content_parts": body.content_parts,
    }
    await _enrich_agent_config(runtime_body, claims, user_token)

    async def generate():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", f"{base}/message", json=runtime_body, timeout=None,
                ) as resp:
                    if resp.status_code != 200:
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
                        # Tool events get pushed into parent's session for
                        # inline rendering and final assembly merge.
                        if etype in ("tool_use", "tool_result"):
                            tagged = {**event, "parent_tool_use_id": parent_tool_use_id}
                            await redis_client.publish_message(body.parent_session_id, tagged)
                            await redis_client.append_a2a_event(
                                body.parent_session_id, parent_tool_use_id, tagged,
                            )
                        # Always forward the raw event to the caller (parent A2A server).
                        yield f"data: {json.dumps(event)}\n\n".encode()
        except httpx.HTTPError:
            logger.exception("A2A SSE proxy error for session %s", body.parent_session_id)
            yield (
                f"data: {json.dumps({'type': 'error', 'message': 'Sub-agent runtime unreachable'})}\n\n"
            ).encode()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class _CleanupBody(BaseModel):
    runtime_endpoint: str | None = None
    agent_id: str


@router.delete("/sessions/{session_id}")
async def cleanup_session(session_id: str, body: _CleanupBody):
    """Tell the runtime to drop its workspace entry for this (agent, session).

    Safe to hit any pod in the env — the RWX PVC means every pod sees the
    same `/workspace-root/sessions/{sid}/agents/{aid}/` directory.
    """
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

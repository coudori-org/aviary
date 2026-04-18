"""Drives one runtime→Redis SSE proxy round.

Separated from the router so the lifecycle (status transitions, metrics,
assembly) lives in one place and endpoints stay thin. The `/message` and
`/a2a` paths share the proxy shape but not the state-machine (A2A
forwards SSE to the caller rather than buffering to Redis), so A2A has
its own generator inline in the router — the assembly + terminal-state
bookkeeping here is specific to `/message`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import httpx

from app import assembly, metrics, redis_client
from app.routing import resolve_runtime_base

logger = logging.getLogger(__name__)


class _StreamLifecycle:
    """Redis status-bit bookkeeping for one stream's lifetime. Collapses the
    `set_stream_status` / `set_session_status` / metric transitions that
    used to be sprinkled through `_drive_stream`."""

    def __init__(self, session_id: str, stream_id: str) -> None:
        self.session_id = session_id
        self.stream_id = stream_id

    async def begin(self) -> None:
        await redis_client.set_stream_status(self.stream_id, "streaming")
        await redis_client.set_session_status(self.session_id, "streaming")
        await redis_client.set_session_latest_stream(self.session_id, self.stream_id)
        metrics.active_streams.inc()

    async def mark_error(self) -> None:
        await redis_client.set_stream_status(self.stream_id, "error")
        metrics.publish_requests_total.labels(status="error").inc()

    async def mark_aborted(self) -> None:
        await redis_client.set_stream_status(self.stream_id, "aborted")
        metrics.publish_requests_total.labels(status="aborted").inc()

    async def mark_complete(self) -> None:
        await redis_client.set_stream_status(self.stream_id, "complete")
        metrics.publish_requests_total.labels(status="complete").inc()

    async def end(self) -> None:
        metrics.active_streams.dec()
        await redis_client.set_session_status(self.session_id, "idle")


async def drive_stream(session_id: str, stream_id: str, body: dict) -> dict:
    """Stream runtime SSE → Redis → assembled text/blocks. Returns the
    terminal shape the router sends back to the caller."""
    agent_config = body["agent_config"]
    base = resolve_runtime_base(agent_config.get("runtime_endpoint"))
    reached_runtime = False
    error_message: str | None = None
    aborted = False
    started = time.monotonic()

    lifecycle = _StreamLifecycle(session_id, stream_id)
    await lifecycle.begin()

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
                            # (it owns DB-consistent ids). Returning the
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
        await lifecycle.end()

    metrics.publish_duration_seconds.observe(time.monotonic() - started)

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
        await lifecycle.mark_error()
        return {"status": "error", "message": error_message, **base_return}

    if aborted:
        await lifecycle.mark_aborted()
        return {"status": "aborted", **base_return}

    await lifecycle.mark_complete()
    return {"status": "complete", **base_return}

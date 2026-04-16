"""Redis writer — the supervisor is the sole writer for session/stream state.

Keys & channels owned by this module:

  session:{sid}:events             pub/sub — every stream event (tagged with stream_id)
  session:{sid}:status             string — "idle" | "streaming"  (TTL 3600s)
  session:{sid}:latest_stream      string — most recent stream_id  (TTL 3600s)
  stream:{sid}:chunks              list   — buffered events for replay (TTL 600s)
  stream:{sid}:status              string — "streaming" | "complete" | "error" | "aborted"  (TTL 600s)
  session:{sid}:a2a:{tool_use_id}  list   — sub-agent events buffered for parent assembly (TTL 600s)
  supervisor:abort                 pub/sub — cross-replica abort fan-out
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import redis.asyncio as redis

from app import metrics
from app.config import settings

logger = logging.getLogger(__name__)

_STREAM_BUFFER_TTL = 600
_SESSION_TTL = 3600
_ABORT_CHANNEL = "supervisor:abort"

_client: redis.Redis | None = None
_pool: redis.ConnectionPool | None = None


async def init_redis() -> None:
    global _client, _pool
    _pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    _client = redis.Redis(connection_pool=_pool)
    try:
        await _client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
    except redis.RedisError:
        logger.warning("Redis not reachable at %s — publishing disabled", settings.redis_url)
        _client = None


async def close_redis() -> None:
    global _client, _pool
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    _client = None
    _pool = None


def _session_channel(session_id: str) -> str:
    return f"session:{session_id}:events"


def _stream_chunks(stream_id: str) -> str:
    return f"stream:{stream_id}:chunks"


def _stream_status(stream_id: str) -> str:
    return f"stream:{stream_id}:status"


def _session_status(session_id: str) -> str:
    return f"session:{session_id}:status"


def _session_latest_stream(session_id: str) -> str:
    return f"session:{session_id}:latest_stream"


def _a2a_key(session_id: str, parent_tool_use_id: str) -> str:
    return f"session:{session_id}:a2a:{parent_tool_use_id}"


def _record_error(operation: str, *, warn: bool = False, extra: str = "") -> None:
    metrics.redis_errors_total.labels(operation=operation).inc()
    if warn:
        logger.warning("%s failed%s", operation, extra, exc_info=True)


async def publish_event(session_id: str, event: dict) -> None:
    if not _client:
        return
    try:
        await _client.publish(_session_channel(session_id), json.dumps(event))
    except redis.RedisError:
        _record_error("publish_event", warn=True, extra=f" for session {session_id}")


async def append_stream_chunk(stream_id: str, event: dict) -> None:
    if not _client:
        return
    try:
        await _client.rpush(_stream_chunks(stream_id), json.dumps(event))
        await _client.expire(_stream_chunks(stream_id), _STREAM_BUFFER_TTL)
    except redis.RedisError:
        _record_error("append_stream_chunk", warn=True, extra=f" for stream {stream_id}")


async def get_stream_chunks(stream_id: str) -> list[dict]:
    if not _client:
        return []
    try:
        raw = await _client.lrange(_stream_chunks(stream_id), 0, -1)
        return [json.loads(r) for r in raw]
    except redis.RedisError:
        _record_error("get_stream_chunks")
        return []


async def set_stream_status(stream_id: str, value: str) -> None:
    if not _client:
        return
    try:
        await _client.set(_stream_status(stream_id), value, ex=_STREAM_BUFFER_TTL)
    except redis.RedisError:
        _record_error("set_stream_status")


async def set_session_status(session_id: str, value: str) -> None:
    if not _client:
        return
    try:
        await _client.set(_session_status(session_id), value, ex=_SESSION_TTL)
    except redis.RedisError:
        _record_error("set_session_status")


async def set_session_latest_stream(session_id: str, stream_id: str) -> None:
    if not _client:
        return
    try:
        await _client.set(_session_latest_stream(session_id), stream_id, ex=_SESSION_TTL)
    except redis.RedisError:
        _record_error("set_session_latest_stream")


async def append_a2a_event(
    session_id: str, parent_tool_use_id: str, event: dict,
) -> None:
    if not _client:
        return
    key = _a2a_key(session_id, parent_tool_use_id)
    try:
        await _client.rpush(key, json.dumps(event))
        await _client.expire(key, _STREAM_BUFFER_TTL)
    except redis.RedisError:
        _record_error("append_a2a_event", warn=True, extra=f" for session {session_id}")


async def get_a2a_events(session_id: str, parent_tool_use_id: str) -> list[dict]:
    if not _client:
        return []
    try:
        raw = await _client.lrange(_a2a_key(session_id, parent_tool_use_id), 0, -1)
        return [json.loads(r) for r in raw]
    except redis.RedisError:
        _record_error("get_a2a_events")
        return []


async def clear_a2a_events(session_id: str, parent_tool_use_id: str) -> None:
    if not _client:
        return
    try:
        await _client.delete(_a2a_key(session_id, parent_tool_use_id))
    except redis.RedisError:
        _record_error("clear_a2a_events")


# ── Cross-replica abort fan-out ─────────────────────────────────────────────

async def publish_abort(stream_id: str) -> None:
    if not _client:
        return
    try:
        await _client.publish(_ABORT_CHANNEL, json.dumps({"stream_id": stream_id}))
    except redis.RedisError:
        _record_error("publish_abort", warn=True)


async def iter_abort_requests() -> AsyncIterator[dict]:
    while True:
        if _client is None:
            await asyncio.sleep(1)
            continue
        pubsub = _client.pubsub()
        try:
            await pubsub.subscribe(_ABORT_CHANNEL)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    yield json.loads(msg["data"])
                except (json.JSONDecodeError, TypeError):
                    logger.warning("malformed abort message: %r", msg.get("data"))
        except redis.RedisError:
            logger.warning("abort subscriber connection lost; retrying in 2s", exc_info=True)
            await asyncio.sleep(2)
        finally:
            try:
                await pubsub.unsubscribe(_ABORT_CHANNEL)
                await pubsub.aclose()
            except redis.RedisError:
                pass

"""Redis publisher + stream buffer for session events.

Shared namespace with the API server (`session:{id}:stream:*`, `session:{id}:messages`).
Supervisor publishes raw runtime events and assembles the final response from
the buffered chunks before returning to the caller.

Also hosts the supervisor-to-supervisor abort fan-out channel
(`supervisor:abort`) used to route abort requests to whichever replica
actually holds the in-flight publish task.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_STREAM_BUFFER_TTL = 600
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


def _channel(session_id: str) -> str:
    return f"session:{session_id}:messages"


def _chunks_key(session_id: str) -> str:
    return f"session:{session_id}:stream:chunks"


def _a2a_key(session_id: str, parent_tool_use_id: str) -> str:
    return f"session:{session_id}:a2a:{parent_tool_use_id}"


async def publish_message(session_id: str, message: dict) -> None:
    if not _client:
        return
    try:
        await _client.publish(_channel(session_id), json.dumps(message))
    except redis.RedisError:
        logger.warning("publish failed for session %s", session_id, exc_info=True)


async def append_stream_chunk(session_id: str, event: dict) -> None:
    if not _client:
        return
    try:
        await _client.rpush(_chunks_key(session_id), json.dumps(event))
        await _client.expire(_chunks_key(session_id), _STREAM_BUFFER_TTL)
    except redis.RedisError:
        logger.warning("append_stream_chunk failed for session %s", session_id, exc_info=True)


async def get_stream_chunks(session_id: str) -> list[dict]:
    if not _client:
        return []
    try:
        raw = await _client.lrange(_chunks_key(session_id), 0, -1)
        return [json.loads(r) for r in raw]
    except redis.RedisError:
        logger.warning("get_stream_chunks failed for session %s", session_id, exc_info=True)
        return []


async def set_stream_status(session_id: str, status: str) -> None:
    if not _client:
        return
    try:
        await _client.set(
            f"session:{session_id}:stream:status", status, ex=_STREAM_BUFFER_TTL,
        )
    except redis.RedisError:
        logger.warning("set_stream_status failed for session %s", session_id, exc_info=True)


async def append_a2a_event(
    session_id: str, parent_tool_use_id: str, event: dict,
) -> None:
    """Buffer a sub-agent tool event for later splicing into the parent's blocks."""
    if not _client:
        return
    key = _a2a_key(session_id, parent_tool_use_id)
    try:
        await _client.rpush(key, json.dumps(event))
        await _client.expire(key, _STREAM_BUFFER_TTL)
    except redis.RedisError:
        logger.warning("append_a2a_event failed for session %s", session_id, exc_info=True)


async def get_a2a_events(session_id: str, parent_tool_use_id: str) -> list[dict]:
    if not _client:
        return []
    try:
        raw = await _client.lrange(_a2a_key(session_id, parent_tool_use_id), 0, -1)
        return [json.loads(r) for r in raw]
    except redis.RedisError:
        logger.warning("get_a2a_events failed for session %s", session_id, exc_info=True)
        return []


async def clear_a2a_events(session_id: str, parent_tool_use_id: str) -> None:
    if not _client:
        return
    try:
        await _client.delete(_a2a_key(session_id, parent_tool_use_id))
    except redis.RedisError:
        logger.warning("clear_a2a_events failed for session %s", session_id, exc_info=True)


# ── Supervisor-to-supervisor abort fan-out ──────────────────────────────────

async def publish_abort(session_id: str, agent_id: str | None) -> None:
    """Broadcast an abort request to every supervisor replica (incl. self)."""
    if not _client:
        return
    try:
        await _client.publish(_ABORT_CHANNEL, json.dumps({
            "session_id": session_id,
            "agent_id": agent_id,
        }))
    except redis.RedisError:
        logger.warning("publish_abort failed", exc_info=True)


async def iter_abort_requests() -> AsyncIterator[dict]:
    """Yield abort requests received on the supervisor:abort channel.

    Auto-reconnects on RedisError. Safe to cancel at any time.
    """
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

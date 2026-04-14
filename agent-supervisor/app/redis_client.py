"""Redis publisher + stream buffer for session events.

Shared namespace with the API server (`session:{id}:stream:*`, `session:{id}:messages`).
Supervisor publishes raw runtime events; API consumes the buffer on completion
and emits the final `done`/`cancelled` events (after DB persistence).
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_STREAM_BUFFER_TTL = 600

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
    key = f"session:{session_id}:stream:chunks"
    try:
        await _client.rpush(key, json.dumps(event))
        await _client.expire(key, _STREAM_BUFFER_TTL)
    except redis.RedisError:
        logger.warning("append_stream_chunk failed for session %s", session_id, exc_info=True)


async def set_stream_status(session_id: str, status: str) -> None:
    if not _client:
        return
    try:
        await _client.set(
            f"session:{session_id}:stream:status", status, ex=_STREAM_BUFFER_TTL,
        )
    except redis.RedisError:
        logger.warning("set_stream_status failed for session %s", session_id, exc_info=True)

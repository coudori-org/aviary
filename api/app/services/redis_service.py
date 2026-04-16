"""Redis client — responsibility split with the supervisor:

- **Supervisor writes** stream events (chunk / thinking / tool_use / …)
  because they originate in the SSE stream it drives.
- **API writes** DB-consistent events and per-user state because only the
  API knows the DB ids and the session participant list:
    * `user_message` — broadcast after the user's WS message is saved
    * `done` / `cancelled` — broadcast after agent message persistence
    * `error` — pre-stream / save-path failures
    * `session:{id}:unread:{uid}` counters

Both publish to the same `session:{id}:events` channel; the API WS relay
subscribes and forwards every event to connected clients. Broadcast via
Redis (rather than direct WS sends) keeps the design ready for
multi-participant / multi-replica deployments.
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

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
        logger.warning("Redis not reachable at %s — reads will return empty", settings.redis_url)
        _client = None


async def close_redis() -> None:
    global _client, _pool
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    _client = None
    _pool = None


def get_client() -> redis.Redis | None:
    return _client


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


async def subscribe(session_id: str):
    if not _client:
        return None
    pubsub = _client.pubsub()
    await pubsub.subscribe(_session_channel(session_id))
    return pubsub


# ── Writes owned by the API (DB-consistent events + unread) ────────────────

async def publish_message(session_id: str, event: dict) -> None:
    """Broadcast a DB-consistent event to every WS watching this session."""
    if not _client:
        return
    try:
        await _client.publish(_session_channel(session_id), json.dumps(event))
    except redis.RedisError:
        logger.warning("publish_message failed for session %s", session_id, exc_info=True)


def _unread_key(session_id: str, user_id: str) -> str:
    return f"session:{session_id}:unread:{user_id}"


async def increment_unread(session_id: str, user_id: str) -> None:
    if not _client:
        return
    try:
        await _client.incr(_unread_key(session_id, user_id))
        await _client.expire(_unread_key(session_id, user_id), 86400)
    except redis.RedisError:
        logger.warning("increment_unread failed for %s/%s", session_id, user_id, exc_info=True)


async def clear_unread(session_id: str, user_id: str) -> None:
    if not _client:
        return
    try:
        await _client.delete(_unread_key(session_id, user_id))
    except redis.RedisError:
        pass


async def get_bulk_unread(session_ids: list[str], user_id: str) -> dict[str, int]:
    if not _client or not session_ids:
        return {sid: 0 for sid in session_ids}
    try:
        raw = await _client.mget([_unread_key(sid, user_id) for sid in session_ids])
        return {
            sid: int(val) if val else 0
            for sid, val in zip(session_ids, raw, strict=True)
        }
    except redis.RedisError:
        return {sid: 0 for sid in session_ids}


async def get_stream_chunks(stream_id: str) -> list[dict]:
    if not _client:
        return []
    try:
        raw = await _client.lrange(_stream_chunks(stream_id), 0, -1)
        return [json.loads(r) for r in raw]
    except redis.RedisError:
        logger.warning("get_stream_chunks failed for stream %s", stream_id, exc_info=True)
        return []


async def get_stream_status(stream_id: str) -> str | None:
    if not _client:
        return None
    try:
        return await _client.get(_stream_status(stream_id))
    except redis.RedisError:
        return None


async def get_session_status(session_id: str) -> str:
    if not _client:
        return "offline"
    try:
        return (await _client.get(_session_status(session_id))) or "idle"
    except redis.RedisError:
        return "offline"


async def get_sessions_status(session_ids: list[str]) -> dict[str, str]:
    if not _client or not session_ids:
        return {sid: "offline" for sid in session_ids}
    try:
        values = await _client.mget([_session_status(sid) for sid in session_ids])
        return {sid: (val or "idle") for sid, val in zip(session_ids, values, strict=True)}
    except redis.RedisError:
        return {sid: "offline" for sid in session_ids}


async def get_latest_stream_id(session_id: str) -> str | None:
    """Return the most recent stream_id the supervisor attached to this session,
    used so a reconnecting WS client can replay any in-flight or just-finished
    stream."""
    if not _client:
        return None
    try:
        return await _client.get(_session_latest_stream(session_id))
    except redis.RedisError:
        return None


async def delete_all_session_keys(session_id: str, user_ids: list[str]) -> None:
    """Best-effort cleanup on session delete."""
    if not _client:
        return
    try:
        latest = await _client.get(_session_latest_stream(session_id))
        keys = [
            _session_channel(session_id),
            _session_status(session_id),
            _session_latest_stream(session_id),
            *[_unread_key(session_id, uid) for uid in user_ids],
        ]
        if latest:
            keys.extend([_stream_chunks(latest), _stream_status(latest)])
        await _client.delete(*keys)
    except redis.RedisError:
        logger.warning("delete_all_session_keys failed for %s", session_id, exc_info=True)

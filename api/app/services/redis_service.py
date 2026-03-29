"""Redis connection management: pub/sub, session cache, job queue."""

import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: redis.ConnectionPool | None = None
_client: redis.Redis | None = None


async def init_redis() -> None:
    """Initialize Redis connection pool. Called on app startup."""
    global _pool, _client
    _pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    _client = redis.Redis(connection_pool=_pool)
    # Verify connectivity
    try:
        await _client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
    except Exception:
        logger.warning("Redis not reachable at %s — pub/sub and caching disabled", settings.redis_url)
        _client = None


async def close_redis() -> None:
    """Close Redis connections. Called on app shutdown."""
    global _client, _pool
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    _client = None
    _pool = None


def get_client() -> redis.Redis | None:
    """Return the shared Redis client (None if unavailable)."""
    return _client


# ── Pub/Sub for WebSocket message broadcasting ───────────────

def _channel_name(session_id: str) -> str:
    return f"session:{session_id}:messages"


async def publish_message(session_id: str, message: dict) -> None:
    """Publish a chat message/event to all subscribers on this session's channel."""
    client = get_client()
    if not client:
        return
    try:
        await client.publish(_channel_name(session_id), json.dumps(message))
    except Exception:
        logger.warning("Redis publish failed for session %s", session_id, exc_info=True)


async def subscribe(session_id: str) -> redis.client.PubSub | None:
    """Subscribe to a session's message channel. Returns a PubSub object."""
    client = get_client()
    if not client:
        return None
    pubsub = client.pubsub()
    await pubsub.subscribe(_channel_name(session_id))
    return pubsub


# ── Session state cache ──────────────────────────────────────

_SESSION_CACHE_TTL = 300  # 5 minutes


async def cache_session_pod(session_id: str, pod_name: str | None, namespace: str | None) -> None:
    """Cache the active Pod info for a session (avoids DB lookup on every WS message)."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:pod"
    if pod_name and namespace:
        await client.hset(key, mapping={"pod_name": pod_name, "namespace": namespace})
        await client.expire(key, _SESSION_CACHE_TTL)
    else:
        await client.delete(key)


async def get_cached_session_pod(session_id: str) -> dict[str, str] | None:
    """Get cached Pod info for a session. Returns {"pod_name": ..., "namespace": ...} or None."""
    client = get_client()
    if not client:
        return None
    key = f"session:{session_id}:pod"
    data = await client.hgetall(key)
    return data if data else None


# ── Online presence tracking ─────────────────────────────────

async def add_ws_connection(session_id: str, user_id: str) -> None:
    """Track that a user has an active WebSocket connection to a session."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:online"
    await client.sadd(key, user_id)
    await client.expire(key, 3600)


async def remove_ws_connection(session_id: str, user_id: str) -> None:
    """Remove a user's WebSocket connection tracking."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:online"
    await client.srem(key, user_id)


async def get_online_users(session_id: str) -> set[str]:
    """Get the set of user IDs currently connected to a session."""
    client = get_client()
    if not client:
        return set()
    key = f"session:{session_id}:online"
    return await client.smembers(key)

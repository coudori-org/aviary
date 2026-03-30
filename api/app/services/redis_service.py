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


# ── Agent deployment cache ─────────────────────────────────

_DEPLOYMENT_CACHE_TTL = 600  # 10 minutes


async def cache_agent_deployment(agent_id: str, namespace: str) -> None:
    """Cache the agent's deployment namespace (avoids DB lookup for routing)."""
    client = get_client()
    if not client:
        return
    key = f"agent:{agent_id}:deployment"
    await client.hset(key, mapping={"namespace": namespace, "service": "agent-runtime-svc"})
    await client.expire(key, _DEPLOYMENT_CACHE_TTL)


async def get_cached_agent_deployment(agent_id: str) -> dict[str, str] | None:
    """Get cached deployment info for an agent. Returns {"namespace": ..., "service": ...} or None."""
    client = get_client()
    if not client:
        return None
    key = f"agent:{agent_id}:deployment"
    data = await client.hgetall(key)
    return data if data else None


async def clear_agent_deployment_cache(agent_id: str) -> None:
    """Clear cached deployment info for an agent."""
    client = get_client()
    if not client:
        return
    await client.delete(f"agent:{agent_id}:deployment")


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


# ── Stream buffer (chunk replay for reconnecting clients) ───

_STREAM_BUFFER_TTL = 600  # 10 minutes


async def append_stream_chunk(session_id: str, chunk_event: dict) -> None:
    """Append a streaming chunk to the session's replay buffer."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:stream:chunks"
    await client.rpush(key, json.dumps(chunk_event))
    await client.expire(key, _STREAM_BUFFER_TTL)


async def get_stream_chunks(session_id: str) -> list[dict]:
    """Get all buffered chunks for replay."""
    client = get_client()
    if not client:
        return []
    key = f"session:{session_id}:stream:chunks"
    raw = await client.lrange(key, 0, -1)
    return [json.loads(r) for r in raw]


async def set_stream_status(session_id: str, status: str) -> None:
    """Set stream status: 'streaming', 'complete', 'error'."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:stream:status"
    await client.set(key, status, ex=_STREAM_BUFFER_TTL)


async def get_stream_status(session_id: str) -> str | None:
    """Get current stream status."""
    client = get_client()
    if not client:
        return None
    key = f"session:{session_id}:stream:status"
    return await client.get(key)


async def set_stream_result(session_id: str, result: str, message_id: str) -> None:
    """Store the completed agent response for late-joining clients."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:stream:result"
    await client.set(key, json.dumps({"content": result, "messageId": message_id}), ex=120)


async def get_stream_result(session_id: str) -> dict | None:
    """Get the completed stream result (content + messageId)."""
    client = get_client()
    if not client:
        return None
    key = f"session:{session_id}:stream:result"
    raw = await client.get(key)
    return json.loads(raw) if raw else None


async def clear_stream_buffer(session_id: str) -> None:
    """Remove all stream buffer keys for a session."""
    client = get_client()
    if not client:
        return
    keys = [
        f"session:{session_id}:stream:chunks",
        f"session:{session_id}:stream:status",
        f"session:{session_id}:stream:result",
    ]
    await client.delete(*keys)


# ── Session status (for sidebar) ────────────────────────────

async def set_session_status(session_id: str, status: str) -> None:
    """Set session-level status: 'streaming', 'idle', 'offline'."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:status"
    await client.set(key, status, ex=3600)


async def get_session_status(session_id: str) -> str:
    """Get session status."""
    client = get_client()
    if not client:
        return "offline"
    key = f"session:{session_id}:status"
    return await client.get(key) or "offline"


async def get_sessions_status(session_ids: list[str]) -> dict[str, str]:
    """Batch get status for multiple sessions."""
    client = get_client()
    if not client or not session_ids:
        return {}
    pipe = client.pipeline()
    for sid in session_ids:
        pipe.get(f"session:{sid}:status")
    results = await pipe.execute()
    return {sid: (r or "offline") for sid, r in zip(session_ids, results)}


# ── Unread message tracking ─────────────────────────────────

async def increment_unread(session_id: str, user_id: str) -> None:
    """Increment unread count for a user in a session."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:unread:{user_id}"
    await client.incr(key)
    await client.expire(key, 86400)


async def get_unread(session_id: str, user_id: str) -> int:
    """Get unread count for a user in a session."""
    client = get_client()
    if not client:
        return 0
    key = f"session:{session_id}:unread:{user_id}"
    val = await client.get(key)
    return int(val) if val else 0


async def clear_unread(session_id: str, user_id: str) -> None:
    """Clear unread count when user opens a session."""
    client = get_client()
    if not client:
        return
    key = f"session:{session_id}:unread:{user_id}"
    await client.delete(key)


async def get_bulk_unread(session_ids: list[str], user_id: str) -> dict[str, int]:
    """Batch get unread counts for multiple sessions."""
    client = get_client()
    if not client or not session_ids:
        return {}
    pipe = client.pipeline()
    for sid in session_ids:
        pipe.get(f"session:{sid}:unread:{user_id}")
    results = await pipe.execute()
    return {sid: int(r) if r else 0 for sid, r in zip(session_ids, results)}

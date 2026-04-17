"""Redis pub/sub + replay buffer for workflow run events.

Channel layout mirrors the session events channel used by the supervisor,
but scoped per workflow run:

  channel  workflow:run:{run_id}:events   — live fan-out (pub/sub)
  list     workflow:run:{run_id}:replay   — bounded replay buffer so a
                                             reconnecting WS can catch up
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from worker.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

REPLAY_TTL_SECONDS = 3600  # 1h — enough for a user to refresh the page


async def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def _channel(run_id: str) -> str:
    return f"workflow:run:{run_id}:events"


def _replay_key(run_id: str) -> str:
    return f"workflow:run:{run_id}:replay"


async def publish_event(run_id: str, event: dict) -> None:
    """Broadcast one event + append to replay buffer atomically."""
    cli = await _get_client()
    payload = json.dumps(event)
    async with cli.pipeline(transaction=False) as pipe:
        pipe.publish(_channel(run_id), payload)
        pipe.rpush(_replay_key(run_id), payload)
        pipe.expire(_replay_key(run_id), REPLAY_TTL_SECONDS)
        await pipe.execute()

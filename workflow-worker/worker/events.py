"""Redis pub/sub for workflow + session events.

Two channels, different consumers:
  workflow:run:{run_id}:events — node/run status, subscribed by the UI
                                   graph; backed by a bounded replay list
                                   so a reconnecting WS can catch up.
  session:{sid}:events         — chat-style events (user_message,
                                   done / cancelled / error); the agent_step
                                   transcript subscribes directly.
"""

from __future__ import annotations

import json
import logging

import redis.asyncio as redis

from worker.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

# TTL refreshes on every publish, so a running workflow never loses its
# buffer. The window only matters after the run finishes: it just needs to
# cover "user refreshes right after the run ends" — post-mortem viewing
# goes through GET /runs/{id}.
REPLAY_TTL_SECONDS = 600


async def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


class WorkflowPublisher:
    """One-stop publisher for every event the worker emits. Callers pass
    domain fields (run_id / node_id / status / …) and the publisher owns
    channel names, payload shape, and the replay buffer."""

    async def node_status(
        self,
        run_id: str,
        node_id: str,
        node_type: str,
        status: str,
        *,
        input_data: dict | None = None,
        output_data: dict | None = None,
        error: str | None = None,
        session_id: str | None = None,
    ) -> None:
        event: dict = {
            "type": "node_status",
            "node_id": node_id,
            "node_type": node_type,
            "status": status,
        }
        if input_data is not None:
            event["input_data"] = input_data
        if output_data is not None:
            event["output_data"] = output_data
        if error:
            event["error"] = error
        if session_id:
            event["session_id"] = session_id
        await self._publish_run(run_id, event)

    async def run_status(self, run_id: str, status: str, *, error: str | None = None) -> None:
        event: dict = {"type": "run_status", "status": status}
        if error:
            event["error"] = error
        await self._publish_run(run_id, event)

    async def session_user_message(
        self, session_id: str, *, message_id: str, sender_id: str | None, content: str,
    ) -> None:
        await self._publish_session(session_id, {
            "type": "user_message",
            "messageId": message_id,
            "sender_id": sender_id,
            "content": content,
        })

    async def session_terminal(
        self, session_id: str, *, message_id: str, status: str, error: str | None = None,
    ) -> None:
        event: dict = {"type": status, "messageId": message_id}
        if status == "error" and error:
            event["message"] = error
        await self._publish_session(session_id, event)

    async def _publish_run(self, run_id: str, event: dict) -> None:
        cli = await _get_client()
        payload = json.dumps(event)
        channel = f"workflow:run:{run_id}:events"
        replay = f"workflow:run:{run_id}:replay"
        async with cli.pipeline(transaction=False) as pipe:
            pipe.publish(channel, payload)
            pipe.rpush(replay, payload)
            pipe.expire(replay, REPLAY_TTL_SECONDS)
            await pipe.execute()

    async def _publish_session(self, session_id: str, event: dict) -> None:
        cli = await _get_client()
        await cli.publish(f"session:{session_id}:events", json.dumps(event))


publisher = WorkflowPublisher()


async def subscribe_session(session_id: str):
    """Subscribe to the supervisor's session event channel. The agent_step
    activity uses this to capture ``stream_started`` for abort routing."""
    cli = await _get_client()
    ps = cli.pubsub()
    await ps.subscribe(f"session:{session_id}:events")
    return ps

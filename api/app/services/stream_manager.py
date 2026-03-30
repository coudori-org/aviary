"""Background streaming task manager.

Decouples Pod-forwarding from WebSocket lifecycle so that:
- Streaming continues even if the client disconnects
- Chunks are buffered in Redis for replay on reconnect
- Agent response is always saved to DB on completion

Routes to agent Pods via K8s Service (agent-runtime-svc) for load-balanced
access across multiple agent replicas.
"""

import asyncio
import json
import logging
import uuid

from sqlalchemy import select

from app.db.models import SessionParticipant
from app.db.session import async_session_factory
from app.services import redis_service, session_service
from app.services.k8s_service import _get_k8s_client

logger = logging.getLogger(__name__)

# In-memory registry of active streaming tasks (per API server process)
_active_streams: dict[str, asyncio.Task] = {}


async def start_stream(
    session_id: str,
    namespace: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    sender_id: str,
) -> None:
    """Launch a background task that streams the Pod response.

    The task survives WebSocket disconnections and ensures the response
    is persisted to DB and buffered in Redis for client replay.
    """
    # Cancel any existing stream for this session (shouldn't happen in normal flow)
    existing = _active_streams.get(session_id)
    if existing and not existing.done():
        logger.warning("Cancelling existing stream for session %s", session_id)
        existing.cancel()

    # Clear previous stream buffer
    await redis_service.clear_stream_buffer(session_id)

    task = asyncio.create_task(
        _run_stream(
            session_id, namespace,
            agent_model_config, agent_instruction,
            agent_tools, agent_mcp_servers, agent_policy,
            content, sender_id,
        )
    )
    _active_streams[session_id] = task

    # Auto-cleanup from registry when done
    def _cleanup(t: asyncio.Task) -> None:
        _active_streams.pop(session_id, None)
    task.add_done_callback(_cleanup)


def is_streaming(session_id: str) -> bool:
    """Check if a stream task is actively running for this session."""
    task = _active_streams.get(session_id)
    return task is not None and not task.done()


async def _run_stream(
    session_id: str,
    namespace: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    sender_id: str,
) -> None:
    """Execute the Pod-forwarding stream as a background task."""
    session_uuid = uuid.UUID(session_id)

    # Set status to streaming
    await redis_service.set_stream_status(session_id, "streaming")
    await redis_service.set_session_status(session_id, "streaming")

    full_response = ""

    try:
        if not namespace:
            placeholder = "[Agent Pod not running — runtime container needed for inference.]"
            chunk_event = {"type": "chunk", "content": placeholder}
            await redis_service.append_stream_chunk(session_id, chunk_event)
            await redis_service.publish_message(session_id, chunk_event)
            full_response = placeholder
        else:
            # Route to Pod via K8s Service proxy (load-balanced across replicas)
            proxy_path = f"/api/v1/namespaces/{namespace}/services/agent-runtime-svc:3000/proxy/message"

            async with _get_k8s_client() as client:
                async with client.stream(
                    "POST",
                    proxy_path,
                    json={
                        "content": content,
                        "session_id": session_id,
                        "model_config_data": agent_model_config,
                        "agent_config": {
                            "instruction": agent_instruction,
                            "tools": agent_tools,
                            "mcp_servers": agent_mcp_servers,
                            "policy": agent_policy,
                        },
                    },
                    timeout=300,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk_data = json.loads(line[6:])

                        if chunk_data.get("type") == "chunk":
                            chunk_text = chunk_data["content"]
                            full_response += chunk_text
                            chunk_event = {"type": "chunk", "content": chunk_text}
                            # Buffer for replay + broadcast to ALL connected clients
                            await redis_service.append_stream_chunk(session_id, chunk_event)
                            await redis_service.publish_message(session_id, chunk_event)
                        elif chunk_data.get("type") == "tool_use":
                            await redis_service.append_stream_chunk(session_id, chunk_data)
                            await redis_service.publish_message(session_id, chunk_data)

        # Save completed response to DB
        async with async_session_factory() as db:
            msg = await session_service.save_message(
                db, session_uuid, "agent", full_response
            )
            await db.commit()
            message_id = str(msg.id)

        # Mark stream as complete
        await redis_service.set_stream_status(session_id, "complete")
        await redis_service.set_stream_result(session_id, full_response, message_id)
        await redis_service.set_session_status(session_id, "idle")

        # Broadcast done event to all connected clients
        done_event = {"type": "done", "messageId": message_id}
        await redis_service.publish_message(session_id, done_event)

        # Increment unread for participants not currently connected
        online_users = await redis_service.get_online_users(session_id)
        async with async_session_factory() as db:
            result = await db.execute(
                select(SessionParticipant.user_id).where(
                    SessionParticipant.session_id == session_uuid
                )
            )
            all_participants = {str(row[0]) for row in result.all()}

        offline_participants = all_participants - online_users
        for uid in offline_participants:
            await redis_service.increment_unread(session_id, uid)

    except asyncio.CancelledError:
        logger.info("Stream cancelled for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")
    except Exception:
        logger.exception("Stream failed for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")

        # Broadcast error
        error_event = {"type": "error", "message": "Agent streaming failed"}
        await redis_service.publish_message(session_id, {**error_event, "_sender": sender_id})

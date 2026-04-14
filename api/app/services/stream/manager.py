"""Stream lifecycle management — start, cancel, and run background streaming tasks.

Decouples agent response streaming from WebSocket lifecycle so that:
- Streaming continues even if the client disconnects
- Chunks are buffered in Redis for replay on reconnect
- Agent response is always saved to DB on completion
"""

import asyncio
import logging
import uuid

import base64

import httpx
from sqlalchemy import select

from aviary_shared.vault import credential_path

from app.db.models import SessionParticipant
from app.db.session import async_session_factory
from app.services import agent_supervisor, redis_service, session_service, vault_service
from app.services.stream.a2a import merge_a2a_events
from app.services.stream.blocks import rebuild_blocks_from_chunks

logger = logging.getLogger(__name__)

_active_streams: dict[str, asyncio.Task] = {}


def build_mcp_config(legacy_mcp_servers: list) -> dict:
    """Build MCP servers config from legacy stdio servers."""
    config: dict = {}
    for srv in legacy_mcp_servers:
        config[srv["name"]] = {"command": srv["command"], "args": srv.get("args", [])}
    return config


async def fetch_user_credentials(user_external_id: str) -> dict[str, str]:
    """Fetch GitHub token for sandbox injection. Empty dict if not stored."""
    secret = await vault_service.read_secret(credential_path(user_external_id, "github-token"))
    if secret is None:
        return {}
    token = secret.get("value")
    return {"github_token": token} if token else {}


async def start_stream(
    session_id: str,
    agent_id: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    user_message_id: uuid.UUID,
    user_token: str = "",
    user_external_id: str = "",
    accessible_agents: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> None:
    """Launch a background task that streams the agent response."""
    existing = _active_streams.get(session_id)
    if existing and not existing.done():
        logger.warning("Cancelling existing stream for session %s", session_id)
        existing.cancel()

    await redis_service.clear_stream_buffer(session_id)

    task = asyncio.create_task(
        _run_stream(
            session_id, agent_id,
            agent_model_config, agent_instruction,
            agent_tools, agent_mcp_servers, agent_policy,
            content, user_message_id, user_token, user_external_id,
            accessible_agents=accessible_agents,
            attachments=attachments,
        )
    )
    _active_streams[session_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        _active_streams.pop(session_id, None)
    task.add_done_callback(_cleanup)


def is_streaming(session_id: str) -> bool:
    """Check if a stream task is actively running for this session."""
    task = _active_streams.get(session_id)
    return task is not None and not task.done()


async def cancel_stream(session_id: str, agent_id: str | None = None) -> bool:
    """Cancel an active stream and abort the agent's session."""
    task = _active_streams.get(session_id)
    if not task or task.done():
        return False

    if agent_id:
        await agent_supervisor.abort_session(agent_id, session_id)

    task.cancel()

    message_id: str | None = None
    try:
        partial = await redis_service.get_stream_chunks(session_id)
        if partial:
            partial_text, blocks_meta = rebuild_blocks_from_chunks(partial)
            await merge_a2a_events(session_id, blocks_meta)

            meta: dict = {"cancelled": True}
            if blocks_meta:
                meta["blocks"] = blocks_meta
            async with async_session_factory() as db:
                msg = await session_service.save_message(
                    db, uuid.UUID(session_id), "agent",
                    partial_text or "[Cancelled]", metadata=meta,
                )
                await db.commit()
                message_id = str(msg.id)
    except Exception:  # Best-effort: partial response save on cancel is non-critical
        logger.warning("Failed to save partial response for cancelled session %s", session_id)

    cancelled_event: dict = {"type": "cancelled"}
    if message_id:
        cancelled_event["messageId"] = message_id
    await redis_service.publish_message(session_id, cancelled_event)

    await redis_service.set_stream_status(session_id, "complete")
    await redis_service.set_session_status(session_id, "idle")
    await redis_service.clear_stream_buffer(session_id)

    return True


async def _run_stream(
    session_id: str,
    agent_id: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    user_message_id: uuid.UUID,
    user_token: str = "",
    user_external_id: str = "",
    accessible_agents: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> None:
    """Execute the agent response stream as a background task."""
    session_uuid = uuid.UUID(session_id)

    await redis_service.set_stream_status(session_id, "streaming")
    await redis_service.set_session_status(session_id, "streaming")
    await redis_service.publish_message(session_id, {"type": "replay_start"})

    async def _drop_user_message_and_fail(reason: str) -> None:
        # Pre-stream failure: roll back the user message we optimistically
        # persisted in the WS handler so the user doesn't end up with a
        # half-conversation when they revisit the session.
        async with async_session_factory() as db:
            await session_service.delete_message(db, user_message_id)
            await db.commit()
        await redis_service.publish_message(
            session_id, {"type": "error", "message": reason, "rollback_message_id": str(user_message_id)},
        )
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")

    try:
        await agent_supervisor.ensure_agent_running(agent_id=agent_id, owner_id="")
        ready = await agent_supervisor.wait_for_agent_ready(agent_id, timeout=90)
    except httpx.HTTPError as e:
        logger.warning("Failed to ensure agent running for session %s", session_id, exc_info=True)
        await _drop_user_message_and_fail(f"Failed to start agent: {e}")
        return

    if not ready:
        await _drop_user_message_and_fail("Agent did not become ready in time")
        return

    credentials: dict[str, str] = {}
    if user_external_id:
        credentials = await fetch_user_credentials(user_external_id)

    # Build content_parts for runtime: resolve file attachments to base64
    content_part: dict = {}
    if content:
        content_part["text"] = content
    if attachments:
        from aviary_shared.db.models import FileUpload
        file_ids = [uuid.UUID(att["file_id"]) for att in attachments]
        async with async_session_factory() as db:
            result = await db.execute(
                select(FileUpload).where(FileUpload.id.in_(file_ids))
            )
            uploads = {str(u.id): u for u in result.scalars().all()}
        resolved = []
        for att in attachments:
            upload = uploads.get(att["file_id"])
            if upload:
                resolved.append({
                    "type": "image",
                    "media_type": upload.content_type,
                    "data": base64.b64encode(upload.data).decode("ascii"),
                })
        if resolved:
            content_part["attachments"] = resolved
    content_parts = [content_part] if content_part else []

    # Reached-runtime = the SDK ack'd our query and the user message is in
    # conversation history, so we must NOT rollback on subsequent errors.
    reached_runtime = False

    try:
        result = await agent_supervisor.publish_stream(
            agent_id=agent_id,
            session_id=session_id,
            body={
                "content_parts": content_parts,
                "session_id": session_id,
                "model_config_data": agent_model_config,
                "agent_config": {
                    "instruction": agent_instruction,
                    "tools": agent_tools,
                    "mcp_servers": build_mcp_config(agent_mcp_servers),
                    "policy": agent_policy,
                    "user_token": user_token,
                    "user_external_id": user_external_id,
                    **({"credentials": credentials} if credentials else {}),
                    **({"accessible_agents": accessible_agents} if accessible_agents else {}),
                },
            },
        )
        reached_runtime = bool(result.get("reached_runtime"))
        if result.get("status") != "complete":
            raise RuntimeError(result.get("message", "Agent runtime error"))

        chunks = await redis_service.get_stream_chunks(session_id)
        full_response, blocks_meta = rebuild_blocks_from_chunks(chunks)
        await merge_a2a_events(session_id, blocks_meta)

        meta = {"blocks": blocks_meta} if blocks_meta else None
        async with async_session_factory() as db:
            msg = await session_service.save_message(
                db, session_uuid, "agent", full_response, metadata=meta
            )
            await db.commit()
            message_id = str(msg.id)

        await redis_service.set_stream_status(session_id, "complete")
        await redis_service.set_stream_result(session_id, full_response, message_id)
        await redis_service.set_session_status(session_id, "idle")

        async with async_session_factory() as db:
            result = await db.execute(
                select(SessionParticipant.user_id).where(
                    SessionParticipant.session_id == session_uuid
                )
            )
            all_participants = {str(row[0]) for row in result.all()}

        for uid in all_participants:
            await redis_service.increment_unread(session_id, uid)

        done_event = {"type": "done", "messageId": message_id}
        await redis_service.publish_message(session_id, done_event)

    except asyncio.CancelledError:
        logger.info("Stream cancelled for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")
    except Exception as exc:  # Best-effort: background task must not crash unhandled
        logger.exception("Stream failed for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")

        reason = str(exc) if str(exc) else "Agent streaming failed"
        error_event: dict = {"type": "error", "message": reason}
        # query() was never invoked — the message is not in SDK conversation
        # history, so rollback the user message to keep DB in sync.
        if not reached_runtime:
            try:
                async with async_session_factory() as db:
                    await session_service.delete_message(db, user_message_id)
                    await db.commit()
                error_event["rollback_message_id"] = str(user_message_id)
            except Exception:
                logger.warning("Failed to rollback user message %s", user_message_id)
        await redis_service.publish_message(session_id, error_event)

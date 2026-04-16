"""Drive a single agent turn from the WS handler.

Flow:
  1. Build the on-the-wire agent_config (full spec — runtime_endpoint,
     model_config, instruction, tools, mcp_servers, accessible_agents).
  2. POST to supervisor /v1/sessions/{sid}/message. Block until the
     supervisor finishes streaming + assembly and returns the assembled
     text/blocks (also on abort — supervisor returns the partial).
  3. Persist the assembled agent response to the DB.
  4. Publish the DB-consistent event (done / cancelled / error) to
     Redis so every WS watching this session sees it, and INCR the
     unread counter for each session participant.

The supervisor owns Redis writes for the live stream events. This module
owns the DB-consistent events because only the API knows the DB ids and
the participant list.
"""

import asyncio
import base64
import logging
import uuid

from sqlalchemy import select

from app.db.session import async_session_factory
from app.services import agent_supervisor, redis_service, session_service
from aviary_shared.db.models import FileUpload

logger = logging.getLogger(__name__)

_active_streams: dict[str, asyncio.Task] = {}


async def start_stream(
    session_id: str,
    agent_config: dict,
    content: str,
    user_message_id: uuid.UUID,
    user_token: str,
    attachments: list[dict] | None = None,
) -> None:
    existing = _active_streams.get(session_id)
    if existing and not existing.done():
        logger.warning("Cancelling existing stream for session %s", session_id)
        existing.cancel()

    task = asyncio.create_task(
        _run_stream(session_id, agent_config, content, user_message_id, user_token, attachments)
    )
    _active_streams[session_id] = task

    def _cleanup(_: asyncio.Task) -> None:
        _active_streams.pop(session_id, None)

    task.add_done_callback(_cleanup)


def is_streaming(session_id: str) -> bool:
    task = _active_streams.get(session_id)
    return task is not None and not task.done()


async def cancel_session(session_id: str) -> bool:
    """Cancel the in-flight stream task for this session, if any. Used by
    session delete — the task.cancel() tears down the httpx→supervisor call,
    which in turn closes the supervisor→runtime stream, aborting the SDK.

    User-initiated cancel from the WebSocket doesn't go through here — the
    client sends an explicit stream_id so the cancel targets a specific
    stream (future multi-participant sessions)."""
    task = _active_streams.get(session_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def _build_content_parts(
    content: str, attachments: list[dict] | None,
) -> list[dict]:
    part: dict = {}
    if content:
        part["text"] = content
    if attachments:
        file_ids = [uuid.UUID(att["file_id"]) for att in attachments]
        async with async_session_factory() as db:
            uploads = {
                str(u.id): u for u in (await db.execute(
                    select(FileUpload).where(FileUpload.id.in_(file_ids))
                )).scalars().all()
            }
        resolved = [
            {
                "type": "image",
                "media_type": uploads[att["file_id"]].content_type,
                "data": base64.b64encode(uploads[att["file_id"]].data).decode("ascii"),
            }
            for att in attachments
            if att["file_id"] in uploads
        ]
        if resolved:
            part["attachments"] = resolved
    return [part] if part else []


async def _persist_and_broadcast(
    session_id: str,
    session_uuid: uuid.UUID,
    full_response: str,
    blocks_meta: list[dict],
    *,
    cancelled: bool,
) -> None:
    """Save the agent message, publish the terminal event, bump unread."""
    meta: dict = {"blocks": blocks_meta} if blocks_meta else {}
    if cancelled:
        meta["cancelled"] = True

    async with async_session_factory() as db:
        msg = await session_service.save_message(
            db, session_uuid, "agent",
            full_response or ("[Cancelled]" if cancelled else ""),
            metadata=meta or None,
        )
        message_id = str(msg.id)
        participants = await session_service.get_session_participants(db, session_uuid)
        await db.commit()

    # INCR before publish: the WS relay DELs unread for the watching user when
    # it forwards `done`/`cancelled`. If we published first, a fast relay could
    # DEL before INCR runs, leaving unread=1 on the session the user just read.
    for uid in participants:
        await redis_service.increment_unread(session_id, uid)

    event = {"type": "cancelled" if cancelled else "done", "messageId": message_id}
    await redis_service.publish_message(session_id, event)


async def _run_stream(
    session_id: str,
    agent_config: dict,
    content: str,
    user_message_id: uuid.UUID,
    user_token: str,
    attachments: list[dict] | None,
) -> None:
    session_uuid = uuid.UUID(session_id)
    content_parts = await _build_content_parts(content, attachments)

    reached_runtime = False

    try:
        result = await agent_supervisor.post_message(
            session_id=session_id,
            user_token=user_token,
            body={
                "session_id": session_id,
                "content_parts": content_parts,
                "agent_config": agent_config,
            },
        )
        reached_runtime = bool(result.get("reached_runtime"))

        status = result.get("status")
        if status == "complete":
            await _persist_and_broadcast(
                session_id, session_uuid,
                result.get("assembled_text", ""),
                result.get("assembled_blocks", []),
                cancelled=False,
            )
        elif status == "aborted":
            await _persist_and_broadcast(
                session_id, session_uuid,
                result.get("assembled_text", ""),
                result.get("assembled_blocks", []),
                cancelled=True,
            )
        else:
            raise RuntimeError(result.get("message", "Agent runtime error"))

    except asyncio.CancelledError:
        logger.info("Stream task cancelled for session %s", session_id)
    except Exception as exc:
        logger.exception("Stream failed for session %s", session_id)
        reason = str(exc) if str(exc) else "Agent streaming failed"
        error_event: dict = {"type": "error", "message": reason}
        # query() was never invoked — the user message isn't in SDK conversation
        # history, so roll it back so the DB stays consistent.
        if not reached_runtime:
            try:
                async with async_session_factory() as db:
                    await session_service.delete_message(db, user_message_id)
                    await db.commit()
                error_event["rollback_message_id"] = str(user_message_id)
            except Exception:
                logger.warning("Failed to rollback user message %s", user_message_id)
        await redis_service.publish_message(session_id, error_event)

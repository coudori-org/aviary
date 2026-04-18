import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.oidc import validate_token
from app.auth.session_store import SESSION_COOKIE_NAME, get_fresh_session
from app.config import settings
from app.db.models import Agent, Session, User
from app.db.session import async_session_factory, get_db
from app.schemas.session import (
    MessagePageResponse,
    MessageResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    SessionSearchMatch,
    SessionSearchResponse,
    SessionTitleUpdate,
)
from app.services import agent_supervisor, redis_service, session_service
from app.services.mention_service import agent_spec, extract_mentions, resolve_mentioned_agents
from app.services.stream import manager as stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# -- Session CRUD --------------------------------------------------

@router.get("/agents/{agent_id}/sessions", response_model=SessionListResponse)
async def list_sessions(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await session_service.list_sessions_for_agent(db, user, agent_id)
    return SessionListResponse(
        items=[SessionResponse.model_validate(s) for s in sessions]
    )


@router.post(
    "/agents/{agent_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    agent_id: uuid.UUID,
    body: SessionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == "deleted":
        raise HTTPException(status_code=410, detail="Agent has been deleted")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this agent")

    session = await session_service.create_session(db, user, agent)
    return SessionResponse.model_validate(session)


@router.get("/sessions/status")
async def get_sessions_status(
    ids: str = Query(..., description="Comma-separated session IDs"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if not session_ids:
        return {"statuses": {}, "unread": {}, "titles": {}}
    statuses = await redis_service.get_sessions_status(session_ids)
    unread = await redis_service.get_bulk_unread(session_ids, str(user.id))
    titles = await session_service.get_session_titles(
        db, [uuid.UUID(sid) for sid in session_ids]
    )
    return {"statuses": statuses, "unread": unread, "titles": titles}


async def _require_session_owner(
    db: AsyncSession, session_id: uuid.UUID, user: User,
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.created_by != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this session")
    return session


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _require_session_owner(db, session_id, user)
    messages, has_more = await session_service.get_session_messages(db, session_id)
    return SessionDetailResponse(
        session=SessionResponse.model_validate(session),
        messages=[MessageResponse.model_validate(m) for m in messages],
        has_more=has_more,
    )


@router.get("/sessions/{session_id}/messages", response_model=MessagePageResponse)
async def get_session_messages_page(
    session_id: uuid.UUID,
    before: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_session_owner(db, session_id, user)
    messages, has_more = await session_service.get_session_messages(
        db, session_id, limit=limit, before=before
    )
    return MessagePageResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        has_more=has_more,
    )


@router.get("/sessions/{session_id}/search", response_model=SessionSearchResponse)
async def search_session_messages(
    session_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_session_owner(db, session_id, user)

    query = q.strip()
    if len(query) < 2:
        return SessionSearchResponse(matches=[])

    pattern = f"%{query}%"
    sql = text("""
        WITH block_matches AS (
            SELECT
                m.id          AS message_id,
                m.created_at  AS created_at,
                (idx - 1)::int AS block_idx,
                CASE
                    WHEN block->>'type' = 'tool_call' THEN
                        coalesce(
                            block->>'tool_use_id',
                            m.id::text || '-saved-' || (idx - 1)::text
                        )
                    WHEN block->>'type' = 'text' THEN
                        m.id::text || '-text-' || (idx - 1)::text
                    WHEN block->>'type' = 'thinking' THEN
                        m.id::text || '-thinking-' || (idx - 1)::text
                    ELSE NULL
                END AS target_id
            FROM messages m
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE
                    WHEN jsonb_typeof(m.metadata->'blocks') = 'array'
                        THEN m.metadata->'blocks'
                    ELSE '[]'::jsonb
                END
            ) WITH ORDINALITY AS t(block, idx)
            WHERE m.session_id = :session_id
              AND (
                  coalesce(block->>'content', '') ILIKE :pattern
                  OR coalesce(block->>'name', '') ILIKE :pattern
                  OR coalesce(block->>'result', '') ILIKE :pattern
                  OR coalesce((block->'input')::text, '') ILIKE :pattern
              )
        ),
        plain_matches AS (
            SELECT
                m.id          AS message_id,
                m.created_at  AS created_at,
                -1            AS block_idx,
                m.id::text || '/' ||
                    (CASE WHEN m.sender_type = 'user' THEN 'user' ELSE 'body' END)
                    AS target_id
            FROM messages m
            WHERE m.session_id = :session_id
              AND m.content ILIKE :pattern
              AND (
                  m.sender_type = 'user'
                  OR jsonb_typeof(m.metadata->'blocks') IS DISTINCT FROM 'array'
                  OR jsonb_array_length(m.metadata->'blocks') = 0
              )
        )
        SELECT message_id, target_id
        FROM (
            SELECT message_id, created_at, block_idx, target_id
            FROM block_matches
            WHERE target_id IS NOT NULL
            UNION ALL
            SELECT message_id, created_at, block_idx, target_id
            FROM plain_matches
        ) all_matches
        ORDER BY created_at DESC, block_idx DESC
        LIMIT 1000
    """)
    result = await db.execute(sql, {"session_id": session_id, "pattern": pattern})
    rows = result.mappings().all()
    return SessionSearchResponse(matches=[
        SessionSearchMatch(message_id=str(row["message_id"]), target_id=str(row["target_id"]))
        for row in rows
    ])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _require_session_owner(db, session_id, user)
    await session_service.delete_session(db, session)
    return None


@router.patch("/sessions/{session_id}/title", response_model=SessionResponse)
async def update_session_title(
    session_id: uuid.UUID,
    body: SessionTitleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_session_owner(db, session_id, user)
    session = await session_service.update_session_title(db, session_id, body.title)
    return SessionResponse.model_validate(session)


# -- WebSocket Chat ------------------------------------------------

async def _handshake_ws(websocket: WebSocket) -> tuple[str, object] | None:
    """Origin + cookie + token checks. Closes the socket on failure."""
    origin = websocket.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        await websocket.close(code=4001, reason="Invalid origin")
        return None

    aviary_session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not aviary_session_id:
        await websocket.close(code=4001, reason="Missing session")
        return None

    initial_session = await get_fresh_session(aviary_session_id)
    if initial_session is None:
        await websocket.close(code=4001, reason="Invalid or expired session")
        return None

    try:
        claims = await validate_token(initial_session.access_token)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return None

    return aviary_session_id, claims


async def _authorize_ws_session(
    websocket: WebSocket, session_id: uuid.UUID, claims,
) -> tuple[Session, Agent | None, User] | None:
    """Resolve the session + owning user + optional agent. Sends error to the
    client and returns None on any failure (workflow-origin sessions have
    ``agent_id IS NULL`` and return agent=None — they're transcript-only)."""
    async with async_session_factory() as db:
        session = await session_service.get_session(db, session_id)
        if not session or session.status != "active":
            await websocket.send_json({"type": "error", "message": "Session not found or inactive"})
            return None

        user = (await db.execute(
            select(User).where(User.external_id == claims.sub)
        )).scalar_one_or_none()
        if not user:
            await websocket.send_json({"type": "error", "message": "User not found"})
            return None
        if session.created_by != user.id:
            await websocket.send_json({"type": "error", "message": "Not the owner of this session"})
            return None

        agent: Agent | None = None
        if session.agent_id is not None:
            agent = (await db.execute(
                select(Agent).where(Agent.id == session.agent_id)
            )).scalar_one_or_none()
            if not agent:
                await websocket.send_json({"type": "error", "message": "Agent not found"})
                return None
        await db.commit()

    return session, agent, user


async def _relay_redis_events(
    websocket: WebSocket, pubsub, session_id_str: str, user_id_str: str,
) -> None:
    """Forward Redis pub/sub events to the client. Terminal events clear the
    unread badge because an active WS means the user is watching."""
    try:
        async for raw_msg in pubsub.listen():
            if raw_msg["type"] != "message":
                continue
            try:
                event = json.loads(raw_msg["data"])
                await websocket.send_json(event)
                if event.get("type") in ("done", "cancelled", "error"):
                    await redis_service.clear_unread(session_id_str, user_id_str)
            except WebSocketDisconnect:
                return
            except Exception as exc:
                # Routine on WS teardown — keep quiet; the outer handler logs
                # real errors with full traceback.
                logger.debug("Relay send failed for session %s: %s", session_id_str, exc)
                return
    except asyncio.CancelledError:
        pass


async def _handle_chat_message(
    websocket: WebSocket,
    data: dict,
    session_id: uuid.UUID,
    session: Session,
    agent: Agent | None,
    user: User,
    aviary_session_id: str,
    user_id_str: str,
) -> bool:
    """Process one inbound chat message. Returns False to close the socket,
    True to keep it open."""
    if agent is None:
        await websocket.send_json({"type": "error", "message": "This session is read-only"})
        return True

    content = (data.get("content") or "").strip()
    attachments = data.get("attachments")
    if not content and not attachments:
        return True

    fresh = await get_fresh_session(aviary_session_id)
    if fresh is None:
        await websocket.send_json({
            "type": "error", "message": "Session expired, please sign in again",
        })
        await websocket.close(code=4001, reason="Session expired")
        return False

    metadata = {"attachments": attachments} if attachments else None
    async with async_session_factory() as db:
        user_msg = await session_service.save_message(
            db, session_id, "user", content, sender_id=user.id, metadata=metadata,
        )
        user_message_id = user_msg.id

        agent = (await db.execute(
            select(Agent).where(Agent.id == session.agent_id)
        )).scalar_one()

        mentioned_slugs = list(dict.fromkeys(
            extract_mentions(agent.instruction or "") + extract_mentions(content)
        ))
        accessible_agents: list[dict] = []
        if mentioned_slugs:
            accessible_agents = await resolve_mentioned_agents(
                db, user, mentioned_slugs, exclude_agent_id=str(agent.id),
            )
        await db.commit()

        agent_config = await agent_spec(agent, db)
        if accessible_agents:
            agent_config["accessible_agents"] = accessible_agents

    session_id_str = str(session_id)
    user_event: dict = {
        "type": "user_message",
        "messageId": str(user_message_id),
        "sender_id": user_id_str,
        "content": content,
    }
    if attachments:
        user_event["attachments"] = attachments
    await redis_service.publish_message(session_id_str, user_event)

    await stream_manager.start_stream(
        session_id=session_id_str,
        agent_config=agent_config,
        content=content,
        user_message_id=user_message_id,
        user_token=fresh.access_token,
        attachments=attachments,
    )
    return True


@router.websocket("/sessions/{session_id}/ws")
async def websocket_chat(websocket: WebSocket, session_id: uuid.UUID):
    handshake = await _handshake_ws(websocket)
    if handshake is None:
        return
    aviary_session_id, claims = handshake

    await websocket.accept()

    session_id_str = str(session_id)
    pubsub = None

    try:
        authorized = await _authorize_ws_session(websocket, session_id, claims)
        if authorized is None:
            return
        session, agent, user = authorized

        await websocket.send_json({"type": "status", "status": "ready"})

        user_id_str = str(user.id)
        await redis_service.clear_unread(session_id_str, user_id_str)
        await _replay_stream_if_needed(websocket, session_id_str)

        pubsub = await redis_service.subscribe(session_id_str)
        relay_task = asyncio.create_task(
            _relay_redis_events(websocket, pubsub, session_id_str, user_id_str)
        )

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "cancel":
                    # Client targets a specific stream_id learned from the
                    # supervisor's `stream_started` event.
                    stream_id = data.get("stream_id")
                    if stream_id:
                        await agent_supervisor.abort_stream(stream_id)
                    continue

                if msg_type != "message":
                    continue

                keep_open = await _handle_chat_message(
                    websocket, data, session_id, session, agent, user,
                    aviary_session_id, user_id_str,
                )
                if not keep_open:
                    return
        finally:
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket handler error for session %s", session_id)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.aclose()


async def _replay_stream_if_needed(websocket: WebSocket, session_id: str) -> None:
    """If a stream is in-flight, replay buffered events to the reconnecting client."""
    stream_id = await redis_service.get_latest_stream_id(session_id)
    if not stream_id:
        return
    status_value = await redis_service.get_stream_status(stream_id)
    if status_value == "streaming":
        await websocket.send_json({"type": "replay_start", "stream_id": stream_id})
        for chunk in await redis_service.get_stream_chunks(stream_id):
            await websocket.send_json(chunk)
        await websocket.send_json({"type": "replay_end", "stream_id": stream_id})

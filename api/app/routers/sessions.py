import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.oidc import validate_token
from app.auth.session_store import SESSION_COOKIE_NAME, get_fresh_session
from app.config import settings
from app.services.mention_service import extract_mentions, resolve_mentioned_agents
from app.db.models import Agent, Session as SessionModel, User
from app.db.session import get_db, async_session_factory
from app.schemas.session import (
    InviteRequest,
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
from app.services import acl_service, agent_supervisor, redis_service, session_service
from app.services.stream import manager as stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# -- Session CRUD (REST) -------------------------------------------

@router.get("/agents/{agent_id}/sessions", response_model=SessionListResponse)
async def list_sessions(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await session_service.list_sessions_for_agent(db, user, agent_id)
    return SessionListResponse(
        items=[SessionResponse.from_orm_session(s) for s in sessions]
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
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.status == "deleted":
        raise HTTPException(status_code=410, detail="Agent has been deleted — no new sessions allowed")

    try:
        await acl_service.check_agent_permission(db, user, agent, "chat")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    team_id = uuid.UUID(body.team_id) if body.team_id else None
    session = await session_service.create_session(db, user, agent, body.type, team_id)
    return SessionResponse.from_orm_session(session)


# -- Session status polling (for sidebar) ---------------------------

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


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    is_participant = await session_service.is_session_participant(db, session_id, user.id)
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant of this session")

    messages, has_more = await session_service.get_session_messages(db, session_id)
    return SessionDetailResponse(
        session=SessionResponse.from_orm_session(session),
        messages=[MessageResponse.from_orm_message(m) for m in messages],
        has_more=has_more,
    )


@router.get("/sessions/{session_id}/messages", response_model=MessagePageResponse)
async def get_session_messages_page(
    session_id: uuid.UUID,
    before: datetime | None = Query(None, description="ISO timestamp cursor; returns messages older than this"),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated message loader for "Show earlier" in chat view.

    Uses `before` as a timestamp cursor (exclusive). The caller passes the
    `created_at` of the currently-oldest loaded message to fetch the previous
    page. Ties on `created_at` are extremely rare (microsecond precision in
    Postgres); accepted as a pragmatic trade-off over a composite cursor.
    """
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    is_participant = await session_service.is_session_participant(db, session_id, user.id)
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant of this session")

    messages, has_more = await session_service.get_session_messages(
        db, session_id, limit=limit, before=before
    )
    return MessagePageResponse(
        messages=[MessageResponse.from_orm_message(m) for m in messages],
        has_more=has_more,
    )


@router.get("/sessions/{session_id}/search", response_model=SessionSearchResponse)
async def search_session_messages(
    session_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Block-level in-chat search.

    Unnests `metadata->'blocks'` and emits one row per matching block.
    `target_id` MUST stay in sync with `restoreBlocks` + the rendered
    `data-search-target` attributes:
      - tool_call: `tool_use_id` (or `{msg_id}-saved-{idx}` fallback)
      - text:      `{msg_id}-text-{idx}`
      - thinking:  `{msg_id}-thinking-{idx}`
      - user msg:  `{msg_id}/user`
      - legacy:    `{msg_id}/body`  (agent w/o blocks)

    Returned latest-message-first, bottom-block-first within a message,
    capped at 1000.
    """
    is_participant = await session_service.is_session_participant(db, session_id, user.id)
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant of this session")

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
    result = await db.execute(
        sql,
        {"session_id": session_id, "pattern": pattern},
    )
    rows = result.mappings().all()
    matches = [
        SessionSearchMatch(
            message_id=str(row["message_id"]),
            target_id=str(row["target_id"]),
        )
        for row in rows
    ]
    return SessionSearchResponse(matches=matches)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only session creator can delete")
    await session_service.delete_session(db, session)
    return None


@router.patch("/sessions/{session_id}/title", response_model=SessionResponse)
async def update_session_title(
    session_id: uuid.UUID,
    body: SessionTitleUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    is_participant = await session_service.is_session_participant(db, session_id, user.id)
    if not is_participant:
        raise HTTPException(status_code=403, detail="Not a participant of this session")
    session = await session_service.update_session_title(db, session_id, body.title)
    return SessionResponse.from_orm_session(session)


@router.post("/sessions/{session_id}/invite", status_code=status.HTTP_201_CREATED)
async def invite_to_session(
    session_id: uuid.UUID,
    body: InviteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only session creator can invite")

    result = await db.execute(select(User).where(User.email == body.email))
    invitee = result.scalar_one_or_none()
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    await session_service.invite_user_to_session(db, session, invitee, user)
    return {"status": "invited"}


# -- WebSocket Chat ------------------------------------------------

@router.websocket("/sessions/{session_id}/ws")
async def websocket_chat(websocket: WebSocket, session_id: uuid.UUID):
    # CSWSH defense — cookies are sent on cross-origin WS handshakes too.
    origin = websocket.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        await websocket.close(code=4001, reason="Invalid origin")
        return

    aviary_session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not aviary_session_id:
        await websocket.close(code=4001, reason="Missing session")
        return

    initial_session = await get_fresh_session(aviary_session_id)
    if initial_session is None:
        await websocket.close(code=4001, reason="Invalid or expired session")
        return

    try:
        claims = await validate_token(initial_session.access_token)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    session_id_str = str(session_id)
    user_id_str: str | None = None
    agent_id_str: str | None = None
    pubsub = None

    try:
        async with async_session_factory() as db:
            session = await session_service.get_session(db, session_id)
            if not session or session.status != "active":
                await websocket.send_json({"type": "error", "message": "Session not found or inactive"})
                return

            result = await db.execute(select(User).where(User.external_id == claims.sub))
            user = result.scalar_one_or_none()
            if not user:
                await websocket.send_json({"type": "error", "message": "User not found"})
                return

            user_id_str = str(user.id)

            is_participant = await session_service.is_session_participant(db, session_id, user.id)
            if not is_participant:
                await websocket.send_json({"type": "error", "message": "Not a session participant"})
                return

            result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
            agent = result.scalar_one_or_none()
            if not agent:
                await websocket.send_json({"type": "error", "message": "Agent not found"})
                return

            agent_id_str = str(agent.id)

            # Ensure agent is running (supervisor handles all provisioning)
            await websocket.send_json({"type": "status", "status": "spawning"})
            try:
                await session_service.ensure_agent_ready(db, agent)
            except (httpx.HTTPError, RuntimeError) as e:
                await websocket.send_json({"type": "status", "status": "offline", "message": f"Failed to start agent: {e}"})
                return

            await db.commit()

        # Wait for agent readiness via supervisor
        await websocket.send_json({"type": "status", "status": "waiting"})
        ready = await agent_supervisor.wait_for_agent_ready(agent_id_str, timeout=90)
        if not ready:
            await websocket.send_json({"type": "status", "status": "offline", "message": "Agent did not become ready in time"})
            return

        await websocket.send_json({"type": "status", "status": "ready"})

        # Track presence and clear unread
        await redis_service.add_ws_connection(session_id_str, user_id_str)
        await redis_service.clear_unread(session_id_str, user_id_str)

        if not stream_manager.is_streaming(session_id_str):
            await redis_service.set_session_status(session_id_str, "idle")

        await _replay_stream_if_needed(websocket, session_id_str)

        pubsub = await redis_service.subscribe(session_id_str)

        async def _relay_from_redis():
            if not pubsub:
                return
            try:
                async for raw_msg in pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    try:
                        data = json.loads(raw_msg["data"])
                        await websocket.send_json(data)
                        # Clear unread when this user receives the done event in
                        # real-time (they're actively viewing the session).
                        if data.get("type") == "done":
                            await redis_service.clear_unread(session_id_str, user_id_str)
                    except WebSocketDisconnect:
                        return
                    except Exception:
                        logger.debug("Relay send failed for session %s", session_id_str, exc_info=True)
                        return
            except asyncio.CancelledError:
                pass

        relay_task = asyncio.create_task(_relay_from_redis())

        # Main message loop
        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "cancel":
                    await stream_manager.cancel_stream(session_id_str, agent_id_str)
                    continue

                if data.get("type") != "message":
                    continue

                content = data.get("content", "").strip()
                if not content:
                    continue

                fresh = await get_fresh_session(aviary_session_id)
                if fresh is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Session expired, please sign in again",
                    })
                    await websocket.close(code=4001, reason="Session expired")
                    return

                async with async_session_factory() as db:
                    user_msg = await session_service.save_message(
                        db, session_id, "user", content, sender_id=user.id,
                    )
                    user_message_id = user_msg.id
                    await db.commit()

                await redis_service.publish_message(session_id_str, {
                    "type": "user_message",
                    "sender_id": user_id_str,
                    "content": content,
                })

                async with async_session_factory() as db:
                    result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
                    agent = result.scalar_one()

                    # Parse @mentions from instruction + current message
                    mentioned_slugs = list(dict.fromkeys(
                        extract_mentions(agent.instruction or "")
                        + extract_mentions(content)
                    ))

                    accessible_agents_list: list[dict] = []
                    if mentioned_slugs:
                        # Resolve user in this DB session for ACL checks
                        user_result = await db.execute(
                            select(User).where(User.external_id == claims.sub)
                        )
                        mention_user = user_result.scalar_one_or_none()
                        if mention_user:
                            agents_resolved = await resolve_mentioned_agents(
                                db, mention_user, mentioned_slugs,
                                exclude_agent_id=str(agent.id),
                            )
                            accessible_agents_list = [
                                a.model_dump() for a in agents_resolved
                            ]

                await stream_manager.start_stream(
                    session_id=session_id_str,
                    agent_id=str(agent.id),
                    agent_model_config=agent.model_config_json,
                    agent_instruction=agent.instruction,
                    agent_tools=agent.tools,
                    agent_mcp_servers=agent.mcp_servers,
                    agent_policy=agent.policy,
                    content=content,
                    user_message_id=user_message_id,
                    user_token=fresh.access_token,
                    user_external_id=claims.sub,
                    accessible_agents=accessible_agents_list or None,
                )
        finally:
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket handler error for session %s", session_id)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        if user_id_str:
            await redis_service.remove_ws_connection(session_id_str, user_id_str)
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.aclose()


async def _replay_stream_if_needed(websocket: WebSocket, session_id: str) -> None:
    """Replay buffered stream chunks or completed response to a reconnecting client."""
    stream_status = await redis_service.get_stream_status(session_id)

    if stream_status == "streaming":
        await websocket.send_json({"type": "replay_start"})
        chunks = await redis_service.get_stream_chunks(session_id)
        for chunk in chunks:
            await websocket.send_json(chunk)
        await websocket.send_json({"type": "replay_end"})

    elif stream_status == "complete":
        result = await redis_service.get_stream_result(session_id)
        if result:
            await websocket.send_json({
                "type": "stream_complete",
                "content": result["content"],
                "messageId": result["messageId"],
            })
        await redis_service.clear_stream_buffer(session_id)

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.oidc import validate_token
from app.db.models import Agent, Session as SessionModel, User
from app.db.session import get_db, async_session_factory
from app.schemas.session import (
    InviteRequest,
    MessageResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
)
from app.services import acl_service, redis_service, session_service, stream_manager

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
    # Verify agent exists and user has chat permission
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        await acl_service.check_agent_permission(db, user, agent, "chat")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    team_id = uuid.UUID(body.team_id) if body.team_id else None
    session = await session_service.create_session(db, user, agent, body.type, team_id)
    return SessionResponse.from_orm_session(session)


# -- Session status polling (for sidebar) ---------------------------
# IMPORTANT: must be registered BEFORE /sessions/{session_id} to avoid
# FastAPI matching "status" as a UUID path parameter.

@router.get("/sessions/status")
async def get_sessions_status(
    ids: str = Query(..., description="Comma-separated session IDs"),
    user: User = Depends(get_current_user),
):
    """Batch get session statuses and unread counts for sidebar polling."""
    session_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if not session_ids:
        return {"statuses": {}, "unread": {}}

    statuses = await redis_service.get_sessions_status(session_ids)
    unread = await redis_service.get_bulk_unread(session_ids, str(user.id))
    return {"statuses": statuses, "unread": unread}


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not user.is_platform_admin:
        is_participant = await session_service.is_session_participant(db, session_id, user.id)
        if not is_participant:
            raise HTTPException(status_code=403, detail="Not a participant of this session")

    messages = await session_service.get_session_messages(db, session_id)
    return SessionDetailResponse(
        session=SessionResponse.from_orm_session(session),
        messages=[MessageResponse.from_orm_message(m) for m in messages],
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await session_service.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.created_by != user.id and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Only session creator can archive")
    session.status = "archived"
    return None


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
    if session.created_by != user.id and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Only session creator can invite")

    # Look up invitee by email
    result = await db.execute(select(User).where(User.email == body.email))
    invitee = result.scalar_one_or_none()
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    await session_service.invite_user_to_session(db, session, invitee, user)
    return {"status": "invited"}


# -- WebSocket Chat ------------------------------------------------

@router.websocket("/sessions/{session_id}/ws")
async def websocket_chat(websocket: WebSocket, session_id: uuid.UUID):
    # Authenticate via query param token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        claims = await validate_token(token)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    session_id_str = str(session_id)
    user_id_str: str | None = None
    pubsub = None

    try:
        async with async_session_factory() as db:
            # Verify session and participation
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
            if not is_participant and not user.is_platform_admin:
                await websocket.send_json({"type": "error", "message": "Not a session participant"})
                return

            # Get agent for deployment routing
            result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
            agent = result.scalar_one_or_none()
            if not agent:
                await websocket.send_json({"type": "error", "message": "Agent not found"})
                return

            # Lazy-create K8s namespace if agent was created before K8s was available
            if not agent.namespace:
                await websocket.send_json({"type": "status", "status": "provisioning"})
                try:
                    from app.services import k8s_service
                    ns_name = await k8s_service.create_agent_namespace(
                        agent_id=str(agent.id),
                        owner_id=str(agent.owner_id),
                        instruction=agent.instruction,
                        tools=agent.tools,
                        policy=agent.policy,
                        mcp_servers=agent.mcp_servers,
                    )
                    agent.namespace = ns_name
                except Exception:
                    await websocket.send_json({"type": "status", "status": "offline", "message": "Failed to provision K8s namespace"})
                    return

            # Ensure agent Deployment is running
            await websocket.send_json({"type": "status", "status": "spawning"})
            try:
                namespace = await session_service.ensure_agent_ready(db, agent)
            except Exception as e:
                await websocket.send_json({"type": "status", "status": "offline", "message": f"Failed to start agent: {e}"})
                return

            await db.commit()

        # Wait for Deployment readiness
        await websocket.send_json({"type": "status", "status": "waiting"})
        ready = await _wait_for_deployment_ready(namespace, timeout=90)
        if not ready:
            await websocket.send_json({"type": "status", "status": "offline", "message": "Agent pods did not become ready in time"})
            return

        await websocket.send_json({"type": "status", "status": "ready"})

        # Track presence and clear unread
        await redis_service.add_ws_connection(session_id_str, user_id_str)
        await redis_service.clear_unread(session_id_str, user_id_str)

        # Set session status to idle (if not currently streaming)
        if not stream_manager.is_streaming(session_id_str):
            await redis_service.set_session_status(session_id_str, "idle")

        # Replay buffered stream if reconnecting during/after streaming
        await _replay_stream_if_needed(websocket, session_id_str)

        # Subscribe to Redis pub/sub channel for this session
        pubsub = await redis_service.subscribe(session_id_str)

        # Background task: relay Redis pub/sub messages to this WebSocket client
        async def _relay_from_redis():
            if not pubsub:
                return
            try:
                async for raw_msg in pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    try:
                        data = json.loads(raw_msg["data"])
                        if data.get("_sender") == user_id_str:
                            continue
                        data.pop("_sender", None)
                        await websocket.send_json(data)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        relay_task = asyncio.create_task(_relay_from_redis())

        # Main message loop
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("type") != "message":
                    continue

                content = data.get("content", "").strip()
                if not content:
                    continue

                # Save user message to DB
                async with async_session_factory() as db:
                    await session_service.save_message(
                        db, session_id, "user", content, sender_id=user.id
                    )
                    await db.commit()

                # Broadcast user message to other participants via Redis
                await redis_service.publish_message(session_id_str, {
                    "type": "user_message",
                    "sender_id": user_id_str,
                    "content": content,
                    "_sender": user_id_str,
                })

                # Re-read agent to get latest namespace
                async with async_session_factory() as db:
                    result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
                    agent = result.scalar_one()

                # Start background stream (non-blocking) — routes via Service
                await stream_manager.start_stream(
                    session_id=session_id_str,
                    namespace=agent.namespace,
                    agent_model_config=agent.model_config_json,
                    agent_instruction=agent.instruction,
                    agent_tools=agent.tools,
                    agent_mcp_servers=agent.mcp_servers,
                    agent_policy=agent.policy,
                    content=content,
                    sender_id=user_id_str,
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
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Cleanup: remove presence and unsubscribe
        if user_id_str:
            await redis_service.remove_ws_connection(session_id_str, user_id_str)
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.aclose()


async def _replay_stream_if_needed(websocket: WebSocket, session_id: str) -> None:
    """Replay buffered stream chunks or completed response to a reconnecting client."""
    stream_status = await redis_service.get_stream_status(session_id)

    if stream_status == "streaming":
        # Active stream — replay buffered chunks, then live chunks continue via pub/sub
        await websocket.send_json({"type": "replay_start"})
        chunks = await redis_service.get_stream_chunks(session_id)
        for chunk in chunks:
            await websocket.send_json(chunk)
        await websocket.send_json({"type": "replay_end"})

    elif stream_status == "complete":
        # Stream finished while user was away — send completed response
        result = await redis_service.get_stream_result(session_id)
        if result:
            await websocket.send_json({
                "type": "stream_complete",
                "content": result["content"],
                "messageId": result["messageId"],
            })
        await redis_service.clear_stream_buffer(session_id)


async def _wait_for_deployment_ready(namespace: str, timeout: int = 120) -> bool:
    """Poll the agent Deployment until at least one Pod is ready or timeout."""
    import time
    from app.services.k8s_service import _get_k8s_client, _k8s_initialized, _load_kubeconfig

    if not _k8s_initialized:
        _load_kubeconfig()

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            async with _get_k8s_client() as client:
                resp = await client.get(
                    f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime"
                )
                if resp.status_code == 200:
                    dep = resp.json()
                    status_info = dep.get("status", {})
                    ready_replicas = status_info.get("readyReplicas", 0)
                    if ready_replicas and ready_replicas >= 1:
                        return True

                    # Check for image pull errors via pod conditions
                    conditions = status_info.get("conditions", [])
                    for cond in conditions:
                        if cond.get("type") == "Available" and cond.get("status") == "True":
                            return True
        except Exception:
            pass

        await asyncio.sleep(2)

    return False

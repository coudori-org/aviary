import asyncio
import json
import uuid

import httpx
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
from app.services import acl_service, redis_service, session_service

router = APIRouter()


# ── Session CRUD (REST) ───────────────────────────────────────

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


# ── WebSocket Chat ────────────────────────────────────────────

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

            # Get agent for pod routing
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

            # Ensure a Pod is running for this session
            await websocket.send_json({"type": "status", "status": "spawning"})
            try:
                pod_name = await session_service.ensure_session_pod(db, session, agent)
            except Exception as e:
                await websocket.send_json({"type": "status", "status": "offline", "message": f"Failed to spawn Pod: {e}"})
                return

            await db.commit()

        # Wait for Pod readiness
        await websocket.send_json({"type": "status", "status": "waiting"})
        ready = await _wait_for_pod_ready(agent.namespace, pod_name, timeout=90)
        if not ready:
            await websocket.send_json({"type": "status", "status": "offline", "message": "Pod did not become ready in time"})
            return

        await websocket.send_json({"type": "status", "status": "ready"})

        # Track presence in Redis
        await redis_service.add_ws_connection(session_id_str, user_id_str)

        # Subscribe to Redis pub/sub channel for this session
        pubsub = await redis_service.subscribe(session_id_str)

        # Background task: relay Redis pub/sub messages to this WebSocket client
        async def _relay_from_redis():
            """Listen for messages published by other connections and forward to this client."""
            if not pubsub:
                return
            try:
                async for raw_msg in pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    try:
                        data = json.loads(raw_msg["data"])
                        # Skip messages originating from this connection
                        if data.get("_sender") == user_id_str:
                            continue
                        # Strip internal fields before forwarding
                        data.pop("_sender", None)
                        await websocket.send_json(data)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        relay_task = asyncio.create_task(_relay_from_redis())

        # Main message loop: receive from client → process → broadcast via Redis
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

                # Re-read session/agent to get latest pod_name
                async with async_session_factory() as db:
                    session = await session_service.get_session(db, session_id)
                    result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
                    agent = result.scalar_one()

                # Forward to runtime Pod and stream response
                try:
                    agent_response = await _forward_to_pod_with_broadcast(
                        websocket, session, agent, content, session_id_str, user_id_str
                    )

                    # Save agent response to DB
                    async with async_session_factory() as db:
                        msg = await session_service.save_message(
                            db, session_id, "agent", agent_response
                        )
                        await db.commit()

                    done_event = {"type": "done", "messageId": str(msg.id)}
                    await websocket.send_json(done_event)

                    # Broadcast completion to other participants
                    await redis_service.publish_message(session_id_str, {
                        **done_event,
                        "_sender": user_id_str,
                    })
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Agent error: {e}",
                    })
        finally:
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("WebSocket handler error for session %s", session_id)
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


async def _forward_to_pod_with_broadcast(
    websocket: WebSocket,
    session: SessionModel,
    agent: Agent,
    content: str,
    session_id_str: str,
    sender_id: str,
) -> str:
    """Forward message to the session Pod, stream chunks to this client,
    and broadcast via Redis pub/sub to other connected participants.

    Returns the full concatenated agent response.
    """
    # In local dev without a running Pod, return a placeholder
    if not session.pod_name or not agent.namespace:
        placeholder = (
            f"[Agent '{agent.name}' would respond here. "
            f"Pod not running — runtime container needed for actual inference.]"
        )
        chunk_event = {"type": "chunk", "content": placeholder}
        await websocket.send_json(chunk_event)
        # Broadcast to other participants
        await redis_service.publish_message(session_id_str, {
            **chunk_event, "_sender": sender_id,
        })
        return placeholder

    # Route to Pod via K8s API proxy (API container is outside K3s network)
    # K8s proxy endpoint: /api/v1/namespaces/{ns}/pods/{pod}:{port}/proxy/{path}
    from app.services.k8s_service import _get_k8s_client

    proxy_path = f"/api/v1/namespaces/{agent.namespace}/pods/{session.pod_name}:3000/proxy/message"
    full_response = ""

    async with _get_k8s_client() as client:
        async with client.stream(
            "POST",
            proxy_path,
            json={
                "content": content,
                "session_id": str(session.id),
                "model_config_data": agent.model_config_json,
                "agent_config": {
                    "instruction": agent.instruction,
                    "tools": agent.tools,
                    "mcp_servers": agent.mcp_servers,
                    "policy": agent.policy,
                },
            },
            timeout=300,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk_data = json.loads(line[6:])
                    if chunk_data.get("type") == "chunk":
                        chunk_text = chunk_data["content"]
                        full_response += chunk_text
                        chunk_event = {"type": "chunk", "content": chunk_text}
                        await websocket.send_json(chunk_event)
                        # Broadcast chunk to other participants via Redis
                        await redis_service.publish_message(session_id_str, {
                            **chunk_event, "_sender": sender_id,
                        })
                    elif chunk_data.get("type") == "tool_use":
                        await websocket.send_json(chunk_data)
                        await redis_service.publish_message(session_id_str, {
                            **chunk_data, "_sender": sender_id,
                        })

    return full_response


async def _wait_for_pod_ready(namespace: str, pod_name: str, timeout: int = 120) -> bool:
    """Poll the Pod's readiness probe via K8s API until it passes or timeout."""
    import time
    from app.services.k8s_service import _get_k8s_client, _k8s_initialized, _load_kubeconfig

    if not _k8s_initialized:
        _load_kubeconfig()

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            async with _get_k8s_client() as client:
                resp = await client.get(
                    f"/api/v1/namespaces/{namespace}/pods/{pod_name}"
                )
                if resp.status_code == 200:
                    pod = resp.json()
                    conditions = pod.get("status", {}).get("conditions", [])
                    for cond in conditions:
                        if cond.get("type") == "Ready" and cond.get("status") == "True":
                            return True

                    # Also check container statuses for crash
                    container_statuses = pod.get("status", {}).get("containerStatuses", [])
                    for cs in container_statuses:
                        waiting = cs.get("state", {}).get("waiting", {})
                        if waiting.get("reason") in ("CrashLoopBackOff", "ErrImagePull", "ErrImageNeverPull"):
                            return False
        except Exception:
            pass

        await asyncio.sleep(2)

    return False

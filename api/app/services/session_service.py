"""Session business logic: CRUD, agent deployment lifecycle, idle timeout."""

import logging
import uuid

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Agent, Message, Session, SessionParticipant, User
from app.services import controller_client, redis_service

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    user: User,
    agent: Agent,
    session_type: str = "private",
    team_id: uuid.UUID | None = None,
) -> Session:
    """Create a new chat session."""
    session = Session(
        agent_id=agent.id,
        type=session_type,
        created_by=user.id,
        team_id=team_id,
    )
    db.add(session)
    await db.flush()

    participant = SessionParticipant(
        session_id=session.id,
        user_id=user.id,
    )
    db.add(participant)
    await db.flush()

    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def list_sessions_for_agent(
    db: AsyncSession, user: User, agent_id: uuid.UUID
) -> list[Session]:
    """List sessions for an agent that the user can access."""
    result = await db.execute(
        select(Session)
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .where(
            Session.agent_id == agent_id,
            Session.status == "active",
            SessionParticipant.user_id == user.id,
        )
        .order_by(Session.created_at.desc())
    )
    return list(result.scalars().all())


async def get_session_messages(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 100
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    sender_type: str,
    content: str,
    sender_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> Message:
    """Save a message and update session timestamp."""
    msg = Message(
        session_id=session_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        metadata_json=metadata or {},
    )
    db.add(msg)

    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one()
    session.last_message_at = datetime.now(timezone.utc)

    if session.title is None and sender_type == "user":
        title = content.strip().split("\n")[0]
        if len(title) > 60:
            title = title[:57] + "..."
        session.title = title

    await db.flush()
    return msg


async def update_session_title(
    db: AsyncSession, session_id: uuid.UUID, title: str
) -> Session:
    """Update session title."""
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one()
    session.title = title
    await db.flush()
    return session


async def invite_user_to_session(
    db: AsyncSession,
    session: Session,
    invitee: User,
    invited_by: User,
) -> SessionParticipant:
    """Invite a user to a session."""
    participant = SessionParticipant(
        session_id=session.id,
        user_id=invitee.id,
        invited_by=invited_by.id,
    )
    db.add(participant)
    await db.flush()
    return participant


async def is_session_participant(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def count_active_sessions(db: AsyncSession, agent_id: uuid.UUID) -> int:
    """Count active (non-archived) sessions for an agent."""
    result = await db.execute(
        select(func.count())
        .select_from(Session)
        .where(Session.agent_id == agent_id, Session.status == "active")
    )
    return result.scalar() or 0


async def delete_session(db: AsyncSession, session: Session) -> None:
    """Full session deletion: cancel stream, clean Redis, hard-delete from DB,
    and conditionally tear down agent K8s resources if this was the last session
    of a soft-deleted agent."""
    from app.services import agent_service, stream_manager

    session_id_str = str(session.id)
    agent_id = session.agent_id

    # 1. Cancel any active stream for this session
    if stream_manager.is_streaming(session_id_str):
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        namespace = agent.namespace if agent else None
        await stream_manager.cancel_stream(session_id_str, namespace)

    # 2. Clean up all Redis keys for this session
    await redis_service.delete_all_session_keys(session_id_str)

    # 3. Hard-delete session from DB (CASCADE removes messages + participants)
    await db.delete(session)
    await db.flush()

    # 4–5. Agent-level cleanup: PVC workspace + conditional K8s teardown
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent:
        # 4. PVC session workspace cleanup
        # Session workspace lives at /workspace/sessions/{session_id}/ on the shared
        # agent PVC (agent-workspace). Cleanup is done via the runtime Pod's HTTP API
        # (DELETE /sessions/{session_id}/workspace), proxied through the Controller.
        # This is best-effort: if the Pod is scaled to zero or unreachable, the
        # orphaned directory remains on the PVC and is cleaned up when the PVC is
        # eventually deleted (agent K8s teardown). To change the cleanup strategy
        # (e.g. use a K8s Job instead), modify controller_client.cleanup_session_workspace()
        # and the corresponding Controller endpoint DELETE /v1/deployments/{ns}/sessions/{sid}.
        if agent.namespace:
            await controller_client.cleanup_session_workspace(
                agent.namespace, session_id_str
            )

        # 5. If owning agent is soft-deleted and this was the last session, clean up K8s
        if agent.status == "deleted":
            remaining = await count_active_sessions(db, agent_id)
            if remaining == 0:
                await agent_service.cleanup_agent_k8s_resources(db, agent)


async def ensure_agent_ready(db: AsyncSession, agent: Agent) -> str:
    """Ensure agent Deployment is running and return namespace for routing."""
    if not agent.namespace:
        raise RuntimeError(f"Agent {agent.id} has no K8s namespace")

    if agent.pod_strategy == "manual" and not agent.deployment_active:
        raise RuntimeError("Agent pods not activated. Admin must activate manually.")

    result = await controller_client.ensure_deployment(
        namespace=agent.namespace,
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        instruction=agent.instruction,
        tools=agent.tools,
        policy=agent.policy or {},
        mcp_servers=agent.mcp_servers or [],
        min_pods=agent.min_pods,
        max_pods=agent.max_pods,
    )

    if not agent.deployment_active or result.get("created"):
        agent.deployment_active = True
        agent.last_activity_at = datetime.now(timezone.utc)
        await db.flush()

    return agent.namespace


async def cleanup_idle_agents(db: AsyncSession) -> int:
    """Scale down Deployments for agents idle longer than the timeout. Returns count."""
    timeout_seconds = settings.default_agent_idle_timeout
    cutoff = datetime.now(timezone.utc).timestamp() - timeout_seconds

    result = await db.execute(
        select(Agent).where(
            Agent.deployment_active.is_(True),
            Agent.status == "active",
        )
    )
    agents = result.scalars().all()

    cleaned = 0
    for agent in agents:
        if agent.last_activity_at and agent.last_activity_at.timestamp() < cutoff:
            if agent.namespace:
                try:
                    await controller_client.scale_to_zero(agent.namespace)
                except Exception:
                    logger.warning("Failed to scale down agent %s", agent.id, exc_info=True)
            agent.deployment_active = False
            cleaned += 1

    if cleaned:
        await db.flush()
    return cleaned

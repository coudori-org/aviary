"""Session business logic: CRUD, agent deployment lifecycle, idle timeout."""

import logging
import uuid

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Agent, Message, Session, SessionParticipant, User
from app.services import deployment_service, k8s_service

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

    # Add creator as participant
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

    # Update last_message_at
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one()
    session.last_message_at = datetime.now(timezone.utc)

    # Auto-set title from first message
    if session.title is None and sender_type == "user":
        session.title = content[:100]

    await db.flush()
    return msg


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


async def ensure_agent_ready(db: AsyncSession, agent: Agent) -> str:
    """Ensure agent Deployment is running and return namespace for routing.

    Handles lazy namespace provisioning and respects pod_strategy.
    """
    if not agent.namespace:
        raise RuntimeError(f"Agent {agent.id} has no K8s namespace")

    # Check pod strategy for manual mode
    if agent.pod_strategy == "manual" and not agent.deployment_active:
        raise RuntimeError("Agent pods not activated. Admin must activate manually.")

    namespace = await deployment_service.ensure_agent_deployment(db, agent)
    return namespace


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
            await deployment_service.scale_to_zero(db, agent)
            cleaned += 1

    if cleaned:
        await db.flush()
    return cleaned

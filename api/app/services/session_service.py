"""Session business logic: CRUD and agent readiness."""

import logging
import uuid

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, Message, Session, SessionParticipant, User
from app.services import agent_supervisor, redis_service

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


async def get_session_titles(
    db: AsyncSession, session_ids: list[uuid.UUID]
) -> dict[str, str | None]:
    """Batch fetch titles for multiple sessions."""
    if not session_ids:
        return {}
    result = await db.execute(
        select(Session.id, Session.title).where(Session.id.in_(session_ids))
    )
    return {str(row[0]): row[1] for row in result.all()}


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
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 50,
    before: datetime | None = None,
) -> tuple[list[Message], bool]:
    """Fetch a page of messages, newest-first-paginated but returned ascending.

    - Without `before`: returns the most recent `limit` messages.
    - With `before`: returns `limit` messages older than the given timestamp.

    Returns `(messages, has_more)` where `has_more` is True if at least one
    additional older message exists beyond the returned page. Implemented
    with a `limit + 1` fetch trick to avoid a separate count query.
    """
    stmt = select(Message).where(Message.session_id == session_id)
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()  # Return ascending for display
    return rows, has_more


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
    and conditionally tear down agent resources if this was the last session
    of a soft-deleted agent."""
    from app.services import agent_service
    from app.services.stream import manager as stream_manager

    session_id_str = str(session.id)
    agent_id = session.agent_id

    # 1. Cancel any active stream for this session
    if stream_manager.is_streaming(session_id_str):
        await stream_manager.cancel_stream(session_id_str, str(agent_id))

    # 2. Clean up all Redis keys for this session
    await redis_service.delete_all_session_keys(session_id_str)

    # 3. Hard-delete session from DB (CASCADE removes messages + participants)
    await db.delete(session)
    await db.flush()

    # 4–5. Agent-level cleanup
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent:
        # 4. Session workspace cleanup (best-effort)
        await agent_supervisor.cleanup_session(str(agent_id), session_id_str)

        # 5. If owning agent is soft-deleted and this was the last session, clean up
        if agent.status == "deleted":
            remaining = await count_active_sessions(db, agent_id)
            if remaining == 0:
                await agent_service.cleanup_agent_resources(db, agent)


async def ensure_agent_ready(db: AsyncSession, agent: Agent) -> None:
    """Ensure agent is running via agent supervisor.

    Fully delegated — the supervisor handles all resource provisioning
    with secure defaults if the agent hasn't been set up yet.
    """
    await agent_supervisor.ensure_agent_running(
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        config={
            "instruction": agent.instruction,
            "tools": agent.tools,
            "mcp_servers": agent.mcp_servers or [],
        },
    )

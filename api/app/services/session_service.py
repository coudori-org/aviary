"""Session CRUD — owner-only (multi-user participants will return under RBAC)."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, Message, Session, User
from app.services import agent_supervisor, redis_service

logger = logging.getLogger(__name__)


async def create_session(db: AsyncSession, user: User, agent: Agent) -> Session:
    session = Session(agent_id=agent.id, created_by=user.id)
    db.add(session)
    await db.flush()
    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_session_titles(
    db: AsyncSession, session_ids: list[uuid.UUID]
) -> dict[str, str | None]:
    if not session_ids:
        return {}
    result = await db.execute(
        select(Session.id, Session.title).where(Session.id.in_(session_ids))
    )
    return {str(row[0]): row[1] for row in result.all()}


async def get_session_participants(
    db: AsyncSession, session_id: uuid.UUID,
) -> list[str]:
    """Return the list of user_ids that should receive events for a session.

    Currently just the session creator — kept behind a helper so that when
    multi-user sessions return the broadcast/unread paths don't change."""
    session = await get_session(db, session_id)
    if session is None:
        return []
    return [str(session.created_by)]


async def list_sessions_for_agent(
    db: AsyncSession, user: User, agent_id: uuid.UUID
) -> list[Session]:
    result = await db.execute(
        select(Session)
        .where(
            Session.agent_id == agent_id,
            Session.status == "active",
            Session.created_by == user.id,
            Session.workflow_run_id.is_(None),
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
    stmt = select(Message).where(Message.session_id == session_id)
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return rows, has_more


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    sender_type: str,
    content: str,
    sender_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> Message:
    msg = Message(
        session_id=session_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        metadata_json=metadata or {},
    )
    db.add(msg)

    session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
    session.last_message_at = datetime.now(timezone.utc)

    if session.title is None and sender_type == "user":
        title = content.strip().split("\n")[0]
        if len(title) > 60:
            title = title[:57] + "..."
        session.title = title

    await db.flush()
    return msg


async def delete_message(db: AsyncSession, message_id: uuid.UUID) -> None:
    msg = await db.get(Message, message_id)
    if msg is not None:
        await db.delete(msg)
        await db.flush()


async def update_session_title(
    db: AsyncSession, session_id: uuid.UUID, title: str
) -> Session:
    session = (await db.execute(select(Session).where(Session.id == session_id))).scalar_one()
    session.title = title
    await db.flush()
    return session


async def count_active_sessions(db: AsyncSession, agent_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Session)
        .where(Session.agent_id == agent_id, Session.status == "active")
    )
    return result.scalar() or 0


async def delete_session(db: AsyncSession, session: Session) -> None:
    """Cancel any active stream, clean Redis, drop the row, then clean the
    runtime workspace. If the owning agent is soft-deleted and this was its
    last session, hard-delete the agent too."""
    from app.services import agent_service
    from app.services.stream import manager as stream_manager

    session_id_str = str(session.id)
    agent_id = session.agent_id

    if stream_manager.is_streaming(session_id_str):
        await stream_manager.cancel_session(session_id_str)

    participants = await get_session_participants(db, session.id)
    await redis_service.delete_all_session_keys(session_id_str, participants)

    await db.delete(session)
    await db.flush()

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent:
        await agent_supervisor.cleanup_session(
            session_id_str,
            agent_id=str(agent_id),
            runtime_endpoint=agent.runtime_endpoint,
        )

        if agent.status == "deleted":
            remaining = await count_active_sessions(db, agent_id)
            if remaining == 0:
                await agent_service.cleanup_agent_resources(db, agent)

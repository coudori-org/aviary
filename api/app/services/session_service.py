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
    await redis_service.publish_user_event(str(user.id), {
        "type": "session_created",
        "session": _session_summary(session),
    })
    return session


def _session_summary(session: Session) -> dict:
    return {
        "id": str(session.id),
        "agent_id": str(session.agent_id) if session.agent_id else None,
        "title": session.title,
        "status": session.status,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "last_message_at": (
            session.last_message_at.isoformat() if session.last_message_at else None
        ),
    }


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
    # Helper kept so multi-user broadcast/unread paths stay stable when RBAC returns.
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
) -> tuple[Message, str | None]:
    # new_title is set on the first user message so callers can publish post-commit.
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

    new_title: str | None = None
    if session.title is None and sender_type == "user":
        title = content.strip().split("\n")[0]
        if len(title) > 60:
            title = title[:57] + "..."
        session.title = title
        new_title = title

    await db.flush()
    return msg, new_title


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
    participants = await get_session_participants(db, session_id)
    for uid in participants:
        await redis_service.publish_user_event(uid, {
            "type": "session_changed",
            "session_id": str(session.id),
            "title": title,
            "agent_id": str(session.agent_id) if session.agent_id else None,
        })
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
    runtime workspace."""
    from app.services.stream import manager as stream_manager

    session_id_str = str(session.id)
    agent_id = session.agent_id

    if stream_manager.is_streaming(session_id_str):
        await stream_manager.cancel_session(session_id_str)

    participants = await get_session_participants(db, session.id)
    await redis_service.delete_all_session_keys(session_id_str, participants)
    for uid in participants:
        await redis_service.publish_user_event(uid, {
            "type": "session_deleted",
            "session_id": session_id_str,
        })

    runtime_endpoint: str | None = None
    if agent_id is not None:
        agent = await db.get(Agent, agent_id)
        if agent is not None:
            runtime_endpoint = agent.runtime_endpoint

    await db.delete(session)
    await db.flush()

    if agent_id is None:
        return

    await agent_supervisor.cleanup_session(
        session_id_str,
        agent_id=str(agent_id),
        runtime_endpoint=runtime_endpoint,
    )

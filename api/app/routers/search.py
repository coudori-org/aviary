"""Full-text search across the caller's own sessions."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.search import MessageSearchHit, MessageSearchResponse

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_RESULTS = 50
SNIPPET_LENGTH = 200
SNIPPET_HALF = SNIPPET_LENGTH // 2
MIN_QUERY_LENGTH = 2


@router.get("/messages", response_model=MessageSearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(MAX_RESULTS, ge=1, le=MAX_RESULTS),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageSearchResponse:
    """Search messages by content substring across sessions the user owns."""
    query = q.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return MessageSearchResponse(items=[], total=0)

    sql = text("""
        SELECT
            m.id AS message_id,
            m.session_id,
            s.title AS session_title,
            s.agent_id,
            a.name AS agent_name,
            a.icon AS agent_icon,
            m.sender_type,
            CASE
                WHEN length(m.content) <= :snippet_length THEN m.content
                ELSE substring(
                    m.content
                    FROM greatest(
                        1,
                        position(lower(:q) in lower(m.content)) - :snippet_half
                    )
                    FOR :snippet_length
                )
            END AS snippet,
            m.created_at
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        JOIN agents a ON a.id = s.agent_id
        WHERE s.created_by = :user_id
          AND m.content ILIKE '%' || :q || '%'
        ORDER BY m.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(
        sql,
        {
            "q": query,
            "user_id": user.id,
            "limit": limit,
            "snippet_length": SNIPPET_LENGTH,
            "snippet_half": SNIPPET_HALF,
        },
    )
    rows = result.mappings().all()
    items = [MessageSearchHit(**dict(row)) for row in rows]
    return MessageSearchResponse(items=items, total=len(items))

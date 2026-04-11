"""Search router — full-text search across messages the caller can access.

Uses PostgreSQL `pg_trgm` GIN index on `messages.content` for fast
ILIKE-based substring matching that handles Korean and other multi-byte
content correctly. ACL is enforced by joining `session_participants`
so only sessions the user has actually been invited to are searched.

Snippets are computed in SQL to keep response size small — for messages
longer than 200 chars, we slice a 200-char window centered on the match.
"""

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

# Hard cap on result count — no pagination in v1, just take the most recent N.
MAX_RESULTS = 50

# Snippet window length around the match (in characters)
SNIPPET_LENGTH = 200
SNIPPET_HALF = SNIPPET_LENGTH // 2

# Minimum query length — single character searches return too much noise
# and don't benefit from the trigram index (trigrams need 3+ chars).
MIN_QUERY_LENGTH = 2


@router.get("/messages", response_model=MessageSearchResponse)
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(MAX_RESULTS, ge=1, le=MAX_RESULTS),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageSearchResponse:
    """Search messages by content substring, scoped to the caller's accessible sessions.

    Returns the most recent N matches ordered by created_at DESC.
    """
    query = q.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return MessageSearchResponse(items=[], total=0)

    # Single SQL query joins messages → sessions → agents and applies the
    # ACL filter via session_participants. Snippet is sliced in SQL.
    #
    # Why raw SQL: the snippet expression and pg_trgm-friendly ILIKE are
    # awkward to express via SQLAlchemy's expression language, and the
    # query is read-only with no ORM mapping needed for the result rows.
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
        JOIN session_participants sp ON sp.session_id = s.id
        JOIN agents a ON a.id = s.agent_id
        WHERE sp.user_id = :user_id
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

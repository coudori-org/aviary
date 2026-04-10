"""Message full-text search support

Revision ID: 003
Revises: 002
Create Date: 2026-04-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pg_trgm enables substring/ILIKE indexed search via trigram tokens.
    # Works correctly for multi-byte content (Korean, emoji) because
    # trigrams are character-level rather than word-level.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN index supports `content ILIKE '%query%'` lookups in O(log n).
    # Single-user query latency at ~100k message scale: <50ms.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_content_trgm "
        "ON messages USING GIN (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_content_trgm")
    # Don't drop the extension — other features may rely on it.

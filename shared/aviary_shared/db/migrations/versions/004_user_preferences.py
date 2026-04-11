"""User preferences JSONB column

Revision ID: 004
Revises: 003
Create Date: 2026-04-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Per-user preferences blob — stores cross-device UI state like sidebar
    # ordering, default model picks, etc. Schema is intentionally loose
    # (JSONB) so frontend features can add keys without backend changes.
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")

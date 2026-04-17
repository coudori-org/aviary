"""Drop unused agents.category column.

The field was only wired to the frontend — no filtering, grouping, or RBAC
consumed it. Removed along with the related form/API surface.

Revision ID: 005
Revises: 004
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("agents")}
    if "category" in cols:
        op.drop_column("agents", "category")


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("agents")}
    if "category" not in cols:
        op.add_column(
            "agents",
            sa.Column("category", sa.String(length=100), nullable=True),
        )

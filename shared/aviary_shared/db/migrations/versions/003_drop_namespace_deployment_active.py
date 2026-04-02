"""Drop namespace and deployment_active columns from agents.

Revision ID: 003
Revises: 002
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("agents", "namespace")
    op.drop_column("agents", "deployment_active")


def downgrade() -> None:
    op.add_column("agents", sa.Column("deployment_active", sa.Boolean, server_default="false", nullable=False))
    op.add_column("agents", sa.Column("namespace", sa.String(255), nullable=True))

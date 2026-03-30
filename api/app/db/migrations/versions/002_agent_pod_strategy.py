"""Add agent pod strategy columns for agent-per-pod architecture.

Revision ID: 002
Revises: 001
Create Date: 2026-03-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("pod_strategy", sa.String(20), server_default="lazy", nullable=False))
    op.add_column("agents", sa.Column("min_pods", sa.Integer, server_default="1", nullable=False))
    op.add_column("agents", sa.Column("max_pods", sa.Integer, server_default="3", nullable=False))
    op.add_column("agents", sa.Column("last_activity_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("deployment_active", sa.Boolean, server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("agents", "deployment_active")
    op.drop_column("agents", "last_activity_at")
    op.drop_column("agents", "max_pods")
    op.drop_column("agents", "min_pods")
    op.drop_column("agents", "pod_strategy")

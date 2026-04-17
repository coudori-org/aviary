"""Workflow versioning + run history.

Adds `workflow_versions`, `workflow_runs`, `workflow_node_runs`. Existing
tables are untouched — `create_all` is a no-op for anything already present.

Revision ID: 002
Revises: 001
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op

from aviary_shared.db.models import Base

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_TABLES = ("workflow_versions", "workflow_runs", "workflow_node_runs")


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for name in reversed(NEW_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {name} CASCADE")

"""Drop ``workflow_runs.run_type`` — it duplicated ``version_id IS NULL``.

Single invariant from now on: ``version_id IS NULL`` ↔ draft run. The
Python model exposes ``run_type`` as a read-only property derived from
``version_id`` so response shapes and callers that inspect a loaded row
keep working unchanged.

Revision ID: 008
Revises: 007
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("workflow_runs")}
    if "run_type" in cols:
        op.drop_column("workflow_runs", "run_type")


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("workflow_runs")}
    if "run_type" in cols:
        return
    op.add_column(
        "workflow_runs",
        sa.Column("run_type", sa.String(length=20), nullable=True),
    )
    # Backfill from version_id so existing rows get the right value, then
    # lock the column NOT NULL to match the pre-008 schema.
    op.execute(
        "UPDATE workflow_runs SET run_type = CASE WHEN version_id IS NULL "
        "THEN 'draft' ELSE 'deployed' END"
    )
    op.alter_column("workflow_runs", "run_type", nullable=False)

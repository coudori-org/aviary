"""Track the first ancestor of a resumed run.

Resume creates a new WorkflowRun row + new Temporal workflow rather than
reusing the source run's id. root_run_id lets artifact storage live under a
stable key across a resume chain — artifacts produced by the source run stay
readable by steps in the resumed run.

Revision ID: 006
Revises: 005
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("workflow_runs")}
    if "root_run_id" not in cols:
        op.add_column(
            "workflow_runs",
            sa.Column("root_run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_workflow_runs_root_run_id",
            "workflow_runs",
            "workflow_runs",
            ["root_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("workflow_runs")}
    if "root_run_id" in cols:
        op.drop_constraint("fk_workflow_runs_root_run_id", "workflow_runs", type_="foreignkey")
        op.drop_column("workflow_runs", "root_run_id")

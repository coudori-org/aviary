"""Support workflow-origin sessions on the shared ``sessions`` table.

agent_step runs are upgraded from ephemeral UUIDs to real Session rows so
the chat REST + WS path can render their history / live stream without a
second set of endpoints. Workflow sessions carry no agent — they're anchored
to (workflow_run_id, node_id) instead.

Revision ID: 007
Revises: 006
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("sessions")}

    op.alter_column("sessions", "agent_id", nullable=True)

    if "workflow_run_id" not in cols:
        op.add_column(
            "sessions",
            sa.Column(
                "workflow_run_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            "fk_sessions_workflow_run_id",
            "sessions",
            "workflow_runs",
            ["workflow_run_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if "node_id" not in cols:
        op.add_column("sessions", sa.Column("node_id", sa.String(255), nullable=True))

    op.create_index(
        "idx_sessions_workflow_run",
        "sessions",
        ["workflow_run_id", "node_id"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_sessions_agent_or_workflow",
        "sessions",
        "agent_id IS NOT NULL OR workflow_run_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sessions_agent_or_workflow", "sessions", type_="check")
    op.drop_index("idx_sessions_workflow_run", table_name="sessions")

    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("sessions")}
    if "node_id" in cols:
        op.drop_column("sessions", "node_id")
    if "workflow_run_id" in cols:
        op.drop_constraint("fk_sessions_workflow_run_id", "sessions", type_="foreignkey")
        op.drop_column("sessions", "workflow_run_id")

    op.alter_column("sessions", "agent_id", nullable=False)

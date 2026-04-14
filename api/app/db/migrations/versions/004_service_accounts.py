"""Service accounts + drop dead infra columns

Replaces ad-hoc egress policy fields with a proper ServiceAccount → SG refs
binding model. Drops columns and policy JSON keys that are no longer consumed
by any live code path after the backend abstraction refactor.

Revision ID: 004
Revises: 003
Create Date: 2026-04-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_SA_NAME = "agent-default-sa"


def upgrade() -> None:
    op.create_table(
        "service_accounts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("sg_refs", JSONB, nullable=False, server_default="[]"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

    # Seed the system default SA — present on every deployment, never deletable.
    op.execute(
        f"""
        INSERT INTO service_accounts (name, description, sg_refs, is_system)
        VALUES (
            '{DEFAULT_SA_NAME}',
            'Default service account — bound to default-sg only',
            '["default-sg"]'::jsonb,
            true
        )
        """
    )

    op.add_column(
        "agents",
        sa.Column(
            "service_account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("service_accounts.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.execute(
        f"""
        UPDATE agents
        SET service_account_id = (SELECT id FROM service_accounts WHERE name = '{DEFAULT_SA_NAME}')
        """
    )
    op.alter_column("agents", "service_account_id", nullable=False)

    # Drop dead infrastructure columns no longer read anywhere.
    op.drop_column("agents", "namespace")
    op.drop_column("agents", "deployment_active")
    op.drop_column("policies", "pod_strategy")
    op.drop_column("policies", "resource_limits")


def downgrade() -> None:
    op.add_column("policies", sa.Column("resource_limits", JSONB, nullable=False, server_default="{}"))
    op.add_column("policies", sa.Column("pod_strategy", sa.String(20), nullable=False, server_default="lazy"))
    op.add_column("agents", sa.Column("deployment_active", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("agents", sa.Column("namespace", sa.String(255), nullable=True))

    op.drop_column("agents", "service_account_id")
    op.drop_table("service_accounts")

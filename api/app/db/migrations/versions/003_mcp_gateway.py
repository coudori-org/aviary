"""MCP Gateway tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # MCP Servers catalog
    op.create_table(
        "mcp_servers",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("transport_type", sa.String(20), server_default="streamable_http", nullable=False),
        sa.Column("connection_config", JSONB, server_default="{}", nullable=False),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("is_platform_provided", sa.Boolean, server_default="false", nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("last_discovered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )

    # MCP Tools (auto-discovered from servers)
    op.create_table(
        "mcp_tools",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "server_id", UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("input_schema", JSONB, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("server_id", "name", name="uq_mcp_tool_server_name"),
    )
    op.create_index("idx_mcp_tools_server", "mcp_tools", ["server_id"])

    # MCP Agent-Tool Bindings
    op.create_table(
        "mcp_agent_tool_bindings",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "agent_id", UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "tool_id", UUID(as_uuid=True),
            sa.ForeignKey("mcp_tools.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_id", "tool_id", name="uq_mcp_binding_agent_tool"),
    )
    op.create_index("idx_mcp_bindings_agent", "mcp_agent_tool_bindings", ["agent_id"])

    # MCP Tool ACL (default-deny)
    op.create_table(
        "mcp_tool_acl",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "server_id", UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "tool_id", UUID(as_uuid=True),
            sa.ForeignKey("mcp_tools.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "team_id", UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("permission", sa.String(20), server_default="use", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="mcp_acl_grantee",
        ),
        sa.UniqueConstraint("server_id", "tool_id", "user_id", name="uq_mcp_acl_user"),
        sa.UniqueConstraint("server_id", "tool_id", "team_id", name="uq_mcp_acl_team"),
    )
    op.create_index("idx_mcp_acl_server", "mcp_tool_acl", ["server_id"])


def downgrade() -> None:
    op.drop_table("mcp_tool_acl")
    op.drop_table("mcp_agent_tool_bindings")
    op.drop_table("mcp_tools")
    op.drop_table("mcp_servers")

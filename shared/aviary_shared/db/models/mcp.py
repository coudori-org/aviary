"""MCP Gateway models — McpServer, McpTool, McpAgentToolBinding, McpToolAcl."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aviary_shared.db.models.base import Base


class McpServer(Base):
    """Registered backend MCP server in the platform catalog."""

    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transport_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="streamable_http", server_default="streamable_http"
    )
    connection_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    tags: Mapped[list] = mapped_column(JSONB, server_default="[]")
    is_platform_provided: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    last_discovered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tools: Mapped[list["McpTool"]] = relationship(
        back_populates="server", cascade="all, delete-orphan", passive_deletes=True
    )
    acl_entries: Mapped[list["McpToolAcl"]] = relationship(
        back_populates="server", cascade="all, delete-orphan", passive_deletes=True
    )


class McpTool(Base):
    """Auto-discovered tool from a backend MCP server."""

    __tablename__ = "mcp_tools"
    __table_args__ = (UniqueConstraint("server_id", "name", name="uq_mcp_tool_server_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_schema: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    server: Mapped["McpServer"] = relationship(back_populates="tools")
    bindings: Mapped[list["McpAgentToolBinding"]] = relationship(
        back_populates="tool", cascade="all, delete-orphan", passive_deletes=True
    )
    acl_entries: Mapped[list["McpToolAcl"]] = relationship(
        back_populates="tool", cascade="all, delete-orphan", passive_deletes=True
    )


class McpAgentToolBinding(Base):
    """Binds an MCP tool to an agent."""

    __tablename__ = "mcp_agent_tool_bindings"
    __table_args__ = (UniqueConstraint("agent_id", "tool_id", name="uq_mcp_binding_agent_tool"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_tools.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    tool: Mapped["McpTool"] = relationship(back_populates="bindings")


class McpToolAcl(Base):
    """ACL rule for MCP tool access. Default-deny: no rule = no access."""

    __tablename__ = "mcp_tool_acl"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="mcp_acl_grantee",
        ),
        UniqueConstraint("server_id", "tool_id", "user_id", name="uq_mcp_acl_user"),
        UniqueConstraint("server_id", "tool_id", "team_id", name="uq_mcp_acl_team"),
        Index("idx_mcp_acl_server", "server_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_tools.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    permission: Mapped[str] = mapped_column(String(20), nullable=False, default="use", server_default="use")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    server: Mapped["McpServer"] = relationship(back_populates="acl_entries")
    tool: Mapped["McpTool | None"] = relationship(back_populates="acl_entries")

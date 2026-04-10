"""Agent, AgentACL, and AgentCredential models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aviary_shared.db.models.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Agent definition
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    model_config_json: Mapped[dict] = mapped_column(
        "model_config", JSONB, nullable=False, server_default="{}"
    )
    tools: Mapped[list] = mapped_column(JSONB, server_default="[]")
    mcp_servers: Mapped[list] = mapped_column(JSONB, server_default="[]")

    # Policy
    policy: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    # Catalog
    visibility: Mapped[str] = mapped_column(String(20), default="private", server_default="private")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Infrastructure (managed by admin console / agent supervisor)
    pod_strategy: Mapped[str] = mapped_column(String(20), default="lazy", server_default="lazy")
    min_pods: Mapped[int] = mapped_column(default=1, server_default="1")
    max_pods: Mapped[int] = mapped_column(default=3, server_default="3")
    last_activity_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="owned_agents")  # noqa: F821
    acl_entries: Mapped[list["AgentACL"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True,
    )
    credentials: Mapped[list["AgentCredential"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True,
    )
    sessions: Mapped[list["Session"]] = relationship(back_populates="agent")  # noqa: F821


class AgentACL(Base):
    __tablename__ = "agent_acl"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="acl_grantee",
        ),
        UniqueConstraint("agent_id", "user_id", name="uq_agent_acl_user"),
        UniqueConstraint("agent_id", "team_id", name="uq_agent_acl_team"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship(back_populates="acl_entries")


class AgentCredential(Base):
    __tablename__ = "agent_credentials"
    __table_args__ = (UniqueConstraint("agent_id", "name", name="uq_agent_credential_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    vault_path: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent: Mapped["Agent"] = relationship(back_populates="credentials")

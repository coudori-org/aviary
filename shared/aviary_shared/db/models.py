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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owned_agents: Mapped[list["Agent"]] = relationship(back_populates="owner")
    team_memberships: Mapped[list["TeamMember"]] = relationship(back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    members: Mapped[list["TeamMember"]] = relationship(back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(50), default="member", server_default="member")

    team: Mapped["Team"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="team_memberships")


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

    # Infrastructure (managed by admin console / agent controller)
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

    owner: Mapped["User"] = relationship(back_populates="owned_agents")
    acl_entries: Mapped[list["AgentACL"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True,
    )
    credentials: Mapped[list["AgentCredential"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True,
    )
    sessions: Mapped[list["Session"]] = relationship(back_populates="agent")


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


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), default="private", server_default="private")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    pod_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    agent: Mapped["Agent"] = relationship(back_populates="sessions")
    creator: Mapped["User"] = relationship(foreign_keys=[created_by])
    participants: Mapped[list["SessionParticipant"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True,
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True,
    )


class SessionParticipant(Base):
    __tablename__ = "session_participants"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="participants")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("idx_messages_session", "session_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    session: Mapped["Session"] = relationship(back_populates="messages")

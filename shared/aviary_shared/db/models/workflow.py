"""Workflow definition — CRUD only. Execution moves to Temporal workers; the
previous in-process engine + run/node-run tables were removed along with ACL."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aviary_shared.db.models.base import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    model_config_json: Mapped[dict] = mapped_column(
        "model_config", JSONB, nullable=False, server_default="{}"
    )

    definition: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        server_default='{"nodes":[],"edges":[],"viewport":{"x":0,"y":0,"zoom":1}}',
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship()  # noqa: F821

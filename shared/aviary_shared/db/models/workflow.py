"""Workflow, versions, runs, and per-node run state.

Execution is driven by a Temporal worker; the API owns CRUD + run-history
persistence, and the worker writes node/run status transitions through an
activity.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, func
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

    # Optional per-workflow runtime endpoint override. NULL → agent_step
    # activities fall back to the supervisor's configured default env.
    runtime_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship()  # noqa: F821
    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="workflow",
        order_by="desc(WorkflowVersion.version)",
        cascade="all, delete-orphan",
    )

    @property
    def current_version(self) -> int | None:
        """Latest deployed version number, or None for never-deployed
        workflows. Reads from the eager-loaded ``versions`` relationship
        so callers must ``selectinload(Workflow.versions)`` before
        touching this outside the async context."""
        return max((v.version for v in self.versions), default=None)


class WorkflowVersion(Base):
    """Immutable snapshot of a workflow's definition taken at deploy time."""

    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    model_config_json: Mapped[dict] = mapped_column(
        "model_config", JSONB, nullable=False, server_default="{}"
    )
    deployed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    deployed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    workflow: Mapped["Workflow"] = relationship(back_populates="versions")


class WorkflowRun(Base):
    """One execution of a workflow. `id` is reused as the Temporal workflow_id."""

    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Draft runs have no version pin. SET NULL so deleting a version does not
    # wipe run history that referenced it. ``version_id IS NULL ↔ draft`` is
    # the single invariant for run provenance — see ``run_type`` below.
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "manual" | "webhook" | "cron"
    trigger_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending", index=True)
    definition_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # NULL on a fresh run; resumed runs inherit the source's root_run_id
    # (or fall back to source.id if the source was itself a root). Artifact
    # storage keys on coalesce(root_run_id, id) so resume chains share a tree.
    root_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    temporal_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    node_runs: Mapped[list["WorkflowNodeRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    @property
    def run_type(self) -> str:
        """Derived from ``version_id``: deployed runs pin a version,
        drafts don't. Read-only — writes happen by (not) setting
        ``version_id`` at insert time."""
        return "deployed" if self.version_id is not None else "draft"


class WorkflowNodeRun(Base):
    """Per-node execution state within a WorkflowRun."""

    __tablename__ = "workflow_node_runs"
    __table_args__ = (UniqueConstraint("run_id", "node_id", name="uq_node_run"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="node_runs")

    @property
    def session_id(self) -> str | None:
        """Chat session for this node's agent_step transcript. Deterministic
        uuid5 over ``(root_run_id or run_id, node_id)`` — must match the
        id the worker uses to create the Session row (see
        ``workflow-worker.worker.activities.agent_step_helpers.step_session_id``)
        so the inspector resolves the transcript endpoint without an extra
        lookup. Requires ``self.run`` eager-loaded."""
        if self.node_type != "agent_step":
            return None
        anchor = self.run.root_run_id or self.run.id
        return str(uuid.uuid5(uuid.UUID(str(anchor)), self.node_id))

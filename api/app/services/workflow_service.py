"""Workflow CRUD + versioning — owner-only.

Run execution is driven by a Temporal worker (separate service). This module
handles the synchronous slice: workflow CRUD, deploy/edit state transitions,
and version history.
"""

import logging
import uuid

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workflow, WorkflowRun, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services import agent_supervisor

logger = logging.getLogger(__name__)


async def create_workflow(db: AsyncSession, user: User, data: WorkflowCreate) -> Workflow:
    existing = await db.execute(select(Workflow).where(Workflow.slug == data.slug))
    if existing.scalar_one_or_none():
        raise ValueError(f"Workflow slug '{data.slug}' already exists")

    workflow = Workflow(
        name=data.name,
        slug=data.slug,
        description=data.description,
        owner_id=user.id,
        model_config_json=data.model_config_data.model_dump(),
        runtime_endpoint=data.runtime_endpoint or None,
    )
    db.add(workflow)
    await db.flush()
    return workflow


async def get_workflow(db: AsyncSession, workflow_id: uuid.UUID) -> Workflow | None:
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.status != "deleted")
    )
    return result.scalar_one_or_none()


async def list_workflows_for_user(
    db: AsyncSession, user: User, offset: int = 0, limit: int = 50
) -> tuple[list[Workflow], int]:
    base_query = select(Workflow).where(
        Workflow.status != "deleted", Workflow.owner_id == user.id,
    )
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
    result = await db.execute(
        base_query.order_by(Workflow.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_workflow(db: AsyncSession, workflow: Workflow, data: WorkflowUpdate) -> Workflow:
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.definition is not None:
        workflow.definition = data.definition
    if data.model_config_data is not None:
        workflow.model_config_json = data.model_config_data.model_dump()
    # Treat an explicitly-set empty string as a clear (NULL) so admin can
    # revert a workflow back to the default environment.
    if data.runtime_endpoint is not None:
        workflow.runtime_endpoint = data.runtime_endpoint.strip() or None
    await db.flush()
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    # Collect every distinct root_run_id (or run.id when root is null) for
    # this workflow so we can ask the supervisor to wipe each artifact tree
    # before the CASCADE drops the rows. Best-effort — artifact removal is
    # not transactional with the DB delete.
    rows = await db.execute(
        select(distinct(func.coalesce(WorkflowRun.root_run_id, WorkflowRun.id)))
        .where(WorkflowRun.workflow_id == workflow.id)
    )
    roots = [str(r) for r in rows.scalars().all() if r is not None]
    runtime_endpoint = workflow.runtime_endpoint
    for root in roots:
        try:
            await agent_supervisor.cleanup_workflow_artifacts(root, runtime_endpoint)
        except Exception:  # noqa: BLE001
            logger.warning("Artifact cleanup failed for root=%s", root, exc_info=True)

    await db.delete(workflow)
    await db.flush()


async def current_version_number(db: AsyncSession, workflow_id: uuid.UUID) -> int | None:
    result = await db.execute(
        select(func.max(WorkflowVersion.version)).where(
            WorkflowVersion.workflow_id == workflow_id
        )
    )
    return result.scalar_one_or_none()


async def _cleanup_terminal_drafts(
    db: AsyncSession, workflow_id: uuid.UUID,
) -> None:
    """Delete finished draft runs for this workflow.

    Both deploy and cancel-edit close out an edit cycle — the scratch
    runs produced during that cycle are no longer interesting and
    clutter the history list. Cascade FKs (workflow_node_runs and
    sessions via workflow_run_id) remove dependent rows in one go.
    In-flight drafts are spared so the user can still watch them.
    """
    await db.execute(
        delete(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.run_type == "draft",
            WorkflowRun.status.in_(("completed", "failed", "cancelled")),
        )
    )


async def deploy_workflow(db: AsyncSession, workflow: Workflow, user: User) -> WorkflowVersion:
    """Snapshot the current definition as a new immutable version.

    Each deploy always creates a new version — even if the definition is
    unchanged. The user action itself is what we're recording. Terminal
    draft runs accumulated during the previous edit cycle are cleaned up
    here: deploy is the natural "commit" boundary.
    """
    latest = await current_version_number(db, workflow.id)
    next_version = (latest or 0) + 1

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version=next_version,
        definition=workflow.definition,
        model_config_json=workflow.model_config_json or {},
        deployed_by=user.id,
    )
    db.add(version)
    workflow.status = "deployed"

    await _cleanup_terminal_drafts(db, workflow.id)
    await db.flush()
    return version


async def mark_workflow_draft(db: AsyncSession, workflow: Workflow) -> Workflow:
    workflow.status = "draft"
    await db.flush()
    return workflow


async def cancel_edit(db: AsyncSession, workflow: Workflow) -> Workflow:
    """Discard in-progress draft edits and restore the latest deployed
    version. The inverse of ``mark_workflow_draft`` after an Edit click:
    the user decided not to keep their changes, so we reset
    ``definition`` / ``model_config_json`` from the most recent
    WorkflowVersion snapshot and flip status back to "deployed".

    Requires at least one deployed version — there's nothing to revert
    to otherwise. Draft runs accumulated during the abandoned edit
    cycle are cleaned up, same as deploy.
    """
    latest_version = (await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow.id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )).scalar_one_or_none()
    if latest_version is None:
        raise ValueError("Workflow has no deployed version to revert to")

    workflow.definition = latest_version.definition
    workflow.model_config_json = latest_version.model_config_json or {}
    workflow.status = "deployed"

    await _cleanup_terminal_drafts(db, workflow.id)
    await db.flush()
    return workflow


async def list_workflow_versions(
    db: AsyncSession, workflow_id: uuid.UUID
) -> list[WorkflowVersion]:
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
    )
    return list(result.scalars().all())

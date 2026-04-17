"""Workflow run orchestration.

Couples the DB row (authoritative source for owners / history) with the
Temporal workflow handle. Trigger path: insert pending row → start
Temporal workflow reusing the row id as the workflow_id. Cancel path:
signal Temporal; the worker persists the final `cancelled` status.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, Workflow, WorkflowRun, WorkflowVersion
from app.schemas.workflow import WorkflowRunCreate
from app.services import temporal_client
from aviary_shared.workflow_types import WorkflowRunInput


async def _latest_version(db: AsyncSession, workflow_id: uuid.UUID) -> WorkflowVersion | None:
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_run(
    db: AsyncSession, workflow: Workflow, user: User, body: WorkflowRunCreate,
    user_token: str | None = None,
) -> WorkflowRun:
    """Insert the run row, hand off to Temporal, return the persisted row.

    Raises `ValueError` when the caller asks for a deployed run but no
    version has been published yet. Router converts this to HTTP 400.
    """
    if body.run_type == "deployed":
        version = await _latest_version(db, workflow.id)
        if version is None:
            raise ValueError("Workflow has no deployed version yet")
        definition_snapshot = version.definition
        version_id = version.id
    else:
        definition_snapshot = workflow.definition
        version_id = None

    run = WorkflowRun(
        workflow_id=workflow.id,
        version_id=version_id,
        run_type=body.run_type,
        trigger_type=body.trigger_type,
        trigger_data=body.trigger_data or {},
        triggered_by=user.id,
        status="pending",
        definition_snapshot=definition_snapshot,
    )
    db.add(run)
    await db.flush()
    # Commit before starting Temporal so the worker's persistence activity
    # (which updates this row by id) always sees it.
    await db.commit()

    temporal_run_id = await temporal_client.start_workflow_run(
        WorkflowRunInput(
            run_id=str(run.id),
            owner_external_id=user.external_id,
            definition_snapshot=definition_snapshot,
            trigger_data=body.trigger_data or {},
            user_token=user_token,
        )
    )
    run.temporal_run_id = temporal_run_id
    await db.commit()
    await db.refresh(run)
    return run


async def cancel_run(run: WorkflowRun) -> None:
    await temporal_client.cancel_workflow_run(str(run.id))


async def get_run(
    db: AsyncSession, run_id: uuid.UUID, with_nodes: bool = False,
) -> WorkflowRun | None:
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    if with_nodes:
        stmt = stmt.options(selectinload(WorkflowRun.node_runs))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_runs(
    db: AsyncSession, workflow_id: uuid.UUID,
    include_drafts: bool = False, offset: int = 0, limit: int = 50,
) -> tuple[list[WorkflowRun], int]:
    base = select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
    if not include_drafts:
        base = base.where(WorkflowRun.run_type == "deployed")
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(
        base.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total

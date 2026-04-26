import logging
import uuid

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, Workflow, WorkflowRun, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services import agent_supervisor, temporal_client
from app.errors import ConflictError, StateError

logger = logging.getLogger(__name__)


async def create_workflow(db: AsyncSession, user: User, data: WorkflowCreate) -> Workflow:
    existing = await db.execute(select(Workflow).where(Workflow.slug == data.slug))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Workflow slug '{data.slug}' already exists")

    workflow = Workflow(
        name=data.name,
        slug=data.slug,
        description=data.description,
        owner_id=user.id,
        model_config_json=data.model_config_json.model_dump(),
        runtime_endpoint=data.runtime_endpoint or None,
    )
    db.add(workflow)
    await db.flush()
    # Eager-load `versions` so current_version reads without async lazy-load.
    await db.refresh(workflow, attribute_names=["versions"])
    return workflow


async def get_workflow(db: AsyncSession, workflow_id: uuid.UUID) -> Workflow | None:
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.versions))
        .where(Workflow.id == workflow_id)
    )
    return result.scalar_one_or_none()


async def list_workflows_for_user(
    db: AsyncSession, user: User, offset: int = 0, limit: int = 50
) -> tuple[list[Workflow], int]:
    base_query = select(Workflow).where(Workflow.owner_id == user.id)
    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
    result = await db.execute(
        base_query.options(selectinload(Workflow.versions))
        .order_by(Workflow.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_workflow(db: AsyncSession, workflow: Workflow, data: WorkflowUpdate) -> Workflow:
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.definition is not None:
        workflow.definition = data.definition
    if data.model_config_json is not None:
        workflow.model_config_json = data.model_config_json.model_dump()
    # Empty string clears runtime_endpoint to revert to the default environment.
    if data.runtime_endpoint is not None:
        workflow.runtime_endpoint = data.runtime_endpoint.strip() or None
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    # Force-terminate in-flight runs before DB cascade so workers don't write
    # against rows about to drop.
    in_flight = (await db.execute(
        select(WorkflowRun.id).where(
            WorkflowRun.workflow_id == workflow.id,
            WorkflowRun.status.in_(("pending", "running")),
        )
    )).scalars().all()
    for run_id in in_flight:
        try:
            await temporal_client.terminate_workflow_run(
                str(run_id), reason="workflow deleted",
            )
        except Exception:  # noqa: BLE001
            logger.warning("Temporal terminate failed for run=%s", run_id, exc_info=True)

    # Best-effort artifact cleanup before cascade (not transactional with DB delete).
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


async def _cleanup_terminal_drafts(
    db: AsyncSession, workflow_id: uuid.UUID,
) -> None:
    # In-flight drafts are spared so the user can keep watching them.
    await db.execute(
        delete(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.version_id.is_(None),
            WorkflowRun.status.in_(("completed", "failed", "cancelled")),
        )
    )


async def deploy_workflow(db: AsyncSession, workflow: Workflow, user: User) -> WorkflowVersion:
    next_version = (workflow.current_version or 0) + 1

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
    await db.refresh(workflow, attribute_names=["versions"])
    return version


async def mark_workflow_draft(db: AsyncSession, workflow: Workflow) -> Workflow:
    workflow.status = "draft"
    await db.flush()
    await db.refresh(workflow)
    return workflow


async def cancel_edit(db: AsyncSession, workflow: Workflow) -> Workflow:
    # `versions` is eager-loaded by get_workflow, ordered desc by version.
    latest_version = workflow.versions[0] if workflow.versions else None
    if latest_version is None:
        raise StateError("Workflow has no deployed version to revert to")

    workflow.definition = latest_version.definition
    workflow.model_config_json = latest_version.model_config_json or {}
    workflow.status = "deployed"

    await _cleanup_terminal_drafts(db, workflow.id)
    await db.flush()
    await db.refresh(workflow)
    return workflow


def list_workflow_versions(workflow: Workflow) -> list[WorkflowVersion]:
    return list(workflow.versions)

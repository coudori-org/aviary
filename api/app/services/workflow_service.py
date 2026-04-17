"""Workflow CRUD + versioning — owner-only.

Run execution is driven by a Temporal worker (separate service). This module
handles the synchronous slice: workflow CRUD, deploy/edit state transitions,
and version history.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


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
    await db.flush()
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    await db.delete(workflow)
    await db.flush()


async def current_version_number(db: AsyncSession, workflow_id: uuid.UUID) -> int | None:
    result = await db.execute(
        select(func.max(WorkflowVersion.version)).where(
            WorkflowVersion.workflow_id == workflow_id
        )
    )
    return result.scalar_one_or_none()


async def deploy_workflow(db: AsyncSession, workflow: Workflow, user: User) -> WorkflowVersion:
    """Snapshot the current definition as a new immutable version.

    Each deploy always creates a new version — even if the definition is
    unchanged. The user action itself is what we're recording.
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
    await db.flush()
    return version


async def mark_workflow_draft(db: AsyncSession, workflow: Workflow) -> Workflow:
    workflow.status = "draft"
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

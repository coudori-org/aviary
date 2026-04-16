"""Workflow CRUD. Run execution will return via Temporal workers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_workflow_owner
from app.db.models import User, Workflow
from app.db.session import get_db
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowUpdate,
)
from app.services import workflow_service

router = APIRouter()


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflows, total = await workflow_service.list_workflows_for_user(db, user, offset, limit)
    return WorkflowListResponse(
        items=[WorkflowResponse.from_orm_workflow(w) for w in workflows],
        total=total,
    )


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow = await workflow_service.create_workflow(db, user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return WorkflowResponse.from_orm_workflow(workflow)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow: Workflow = Depends(require_workflow_owner())):
    return WorkflowResponse.from_orm_workflow(workflow)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    body: WorkflowUpdate,
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    workflow = await workflow_service.update_workflow(db, workflow, body)
    await db.refresh(workflow)
    return WorkflowResponse.from_orm_workflow(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    await workflow_service.delete_workflow(db, workflow)
    return None

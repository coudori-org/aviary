"""Workflow management REST API for admin console.

Runtime environments are pre-provisioned via Helm — there are no per-workflow
infrastructure actions (activate/deactivate/restart/scale) in this service
anymore.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Workflow
from app.db import get_db

router = APIRouter()


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {
        "id": str(wf.id),
        "name": wf.name,
        "slug": wf.slug,
        "description": wf.description,
        "owner_id": str(wf.owner_id),
        "status": wf.status,
        "definition": wf.definition,
    }

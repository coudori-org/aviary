"""Workflow list and detail pages."""

import math

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Workflow
from app.db import get_db
from app.routers.pages._templates import templates

router = APIRouter()


@router.get("/workflows", response_class=HTMLResponse)
async def workflow_list(request: Request, page: int = 1, db: AsyncSession = Depends(get_db)):
    per_page = 50
    offset = (page - 1) * per_page

    total_result = await db.execute(select(func.count()).select_from(Workflow))
    total = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total / per_page))

    result = await db.execute(
        select(Workflow).order_by(Workflow.created_at.desc()).offset(offset).limit(per_page)
    )
    workflows = result.scalars().all()

    return templates.TemplateResponse(request, "workflows.html", {
        "workflows": workflows,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    })

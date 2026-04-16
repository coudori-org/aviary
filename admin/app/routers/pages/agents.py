"""Agent list, detail, and delete pages."""

import uuid
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent, Session as SessionModel
from app.db import get_db
from app.routers.pages._templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def agent_list(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    per_page = 20
    offset = (page - 1) * per_page

    count_result = await db.execute(select(func.count()).select_from(Agent))
    total = count_result.scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    result = await db.execute(
        select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(per_page)
    )
    agents = list(result.scalars().all())

    agent_ids = [a.id for a in agents]
    activity_map: dict[str, object] = {}
    if agent_ids:
        activity_rows = await db.execute(
            select(SessionModel.agent_id, func.max(SessionModel.last_message_at))
            .where(SessionModel.agent_id.in_(agent_ids))
            .group_by(SessionModel.agent_id)
        )
        activity_map = {str(aid): ts for aid, ts in activity_rows.all()}

    return templates.TemplateResponse(request, "agents.html", {
        "agents": agents,
        "last_activity": activity_map,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/agents/{agent_id}", response_class=HTMLResponse)
async def agent_detail(
    request: Request, agent_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return HTMLResponse("<h1>Agent not found</h1>", status_code=404)

    last_activity = (await db.execute(
        select(func.max(SessionModel.last_message_at))
        .where(SessionModel.agent_id == agent.id)
    )).scalar_one_or_none()

    flash = request.query_params.get("flash")
    flash_data = None
    if flash:
        flash_data = {"type": "success", "message": flash}
    error = request.query_params.get("error")
    if error:
        flash_data = {"type": "error", "message": error}

    return templates.TemplateResponse(request, "agent_detail.html", {
        "agent": agent,
        "last_activity": last_activity,
        "flash": flash_data,
    })


@router.post("/agents/{agent_id}/update")
async def update_agent_config(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    instruction: str = Form(...),
    runtime_endpoint: str = Form(""),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    agent.name = name
    agent.description = description or None
    agent.instruction = instruction
    agent.runtime_endpoint = runtime_endpoint.strip() or None
    await db.flush()

    return RedirectResponse(f"/agents/{agent_id}?flash=Configuration+saved", status_code=303)


@router.post("/agents/{agent_id}/delete")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse("/?error=Agent+not+found", status_code=303)
    await db.delete(agent)
    await db.flush()
    return RedirectResponse("/?flash=Agent+deleted", status_code=303)

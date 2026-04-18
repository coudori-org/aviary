"""Agent catalog — owner-only for now. Public/team sharing returns with RBAC."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import Agent, User
from app.db.session import get_db
from app.schemas.agent import AgentListResponse, AgentResponse
from app.services import agent_service

router = APIRouter()


@router.get("", response_model=AgentListResponse)
async def browse_catalog(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agents, total = await agent_service.list_agents_for_user(db, user, offset, limit)
    return AgentListResponse(
        items=[AgentResponse.model_validate(a) for a in agents],
        total=total,
    )


@router.get("/search", response_model=AgentListResponse)
async def search_catalog(
    q: str = Query(..., min_length=1),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pattern = f"%{q}%"
    base_query = select(Agent).where(
        Agent.status != "deleted",
        Agent.owner_id == user.id,
        or_(Agent.name.ilike(pattern), Agent.description.ilike(pattern)),
    )

    total = (await db.execute(select(func.count()).select_from(base_query.subquery()))).scalar() or 0
    agents = (await db.execute(
        base_query.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()

    return AgentListResponse(
        items=[AgentResponse.model_validate(a) for a in agents],
        total=total,
    )

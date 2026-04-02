from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
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
    """Browse the agent catalog (respects ACL + visibility)."""
    agents, total = await agent_service.list_agents_for_user(db, user, offset, limit)
    return AgentListResponse(
        items=[AgentResponse.from_orm_agent(a) for a in agents],
        total=total,
    )


@router.get("/categories")
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List agent categories."""
    result = await db.execute(
        select(distinct(Agent.category))
        .where(Agent.status != "deleted", Agent.category.is_not(None))
        .order_by(Agent.category)
    )
    categories = [row[0] for row in result.all()]
    return {"categories": categories}


@router.get("/search", response_model=AgentListResponse)
async def search_catalog(
    q: str = Query(..., min_length=1),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search agents by name or description."""
    from app.db.models import AgentACL, TeamMember
    from sqlalchemy import or_, exists

    search_pattern = f"%{q}%"

    # Build visibility conditions (same as list_agents_for_user)
    conditions = [
        Agent.owner_id == user.id,
        Agent.visibility == "public",
    ]
    conditions.append(
        exists(
            select(AgentACL.id).where(AgentACL.agent_id == Agent.id, AgentACL.user_id == user.id)
        )
    )

    team_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = [row[0] for row in team_ids_result.all()]

    if user_team_ids:
        conditions.append(
            exists(
                select(AgentACL.id).where(
                    AgentACL.agent_id == Agent.id,
                    AgentACL.team_id.in_(user_team_ids),
                )
            )
        )

    base_query = select(Agent).where(
        Agent.status != "deleted",
        or_(Agent.name.ilike(search_pattern), Agent.description.ilike(search_pattern)),
        or_(*conditions),
    )

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )
    agents = result.scalars().all()

    return AgentListResponse(
        items=[AgentResponse.from_orm_agent(a) for a in agents],
        total=total,
    )

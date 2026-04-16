import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_agent_owner
from app.db.models import Agent, User
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentListResponse, AgentResponse, AgentUpdate
from app.services import agent_service

router = APIRouter()


@router.get("", response_model=AgentListResponse)
async def list_agents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agents, total = await agent_service.list_agents_for_user(db, user, offset, limit)
    return AgentListResponse(
        items=[AgentResponse.from_orm_agent(a) for a in agents],
        total=total,
    )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    body: AgentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        agent = await agent_service.create_agent(db, user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return AgentResponse.from_orm_agent(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent: Agent = Depends(require_agent_owner(include_deleted=True))):
    return AgentResponse.from_orm_agent(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    body: AgentUpdate,
    agent: Agent = Depends(require_agent_owner(include_deleted=True)),
    db: AsyncSession = Depends(get_db),
):
    agent = await agent_service.update_agent(db, agent, body)
    await db.refresh(agent)
    return AgentResponse.from_orm_agent(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent: Agent = Depends(require_agent_owner()),
    db: AsyncSession = Depends(get_db),
):
    await agent_service.delete_agent(db, agent)
    return None

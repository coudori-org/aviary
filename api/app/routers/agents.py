import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.agent import AgentCreate, AgentListResponse, AgentResponse, AgentUpdate
from app.services import acl_service, agent_service

router = APIRouter()


@router.get("", response_model=AgentListResponse)
async def list_agents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List agents visible to the current user."""
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
    """Create a new agent."""
    try:
        agent = await agent_service.create_agent(db, user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return AgentResponse.from_orm_agent(agent)


@router.get("/status")
async def get_agents_status(
    ids: str = Query(..., description="Comma-separated agent IDs"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Batch check agent readiness for sidebar display."""
    import asyncio
    from app.services import agent_controller, redis_service

    agent_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if not agent_ids:
        return {"statuses": {}}

    rc = redis_service.get_client()
    cache_ttl = 10

    async def check_one(aid: str) -> tuple[str, str]:
        cache_key = f"agent_readiness:{aid}"

        if rc:
            try:
                cached = await rc.get(cache_key)
                if cached is not None:
                    return aid, cached
            except Exception:
                pass

        try:
            ready = await agent_controller.check_agent_ready(aid)
            result = "ready" if ready else "offline"
        except Exception:
            result = "offline"

        if rc:
            try:
                await rc.set(cache_key, result, ex=cache_ttl)
            except Exception:
                pass

        return aid, result

    results = await asyncio.gather(*[check_one(aid) for aid in agent_ids])
    return {"statuses": dict(results)}


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get agent details (includes deleted agents that still have active sessions)."""
    agent = await agent_service.get_agent(db, agent_id, include_deleted=True)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "view")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    return AgentResponse.from_orm_agent(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update agent configuration (works on deleted agents too)."""
    agent = await agent_service.get_agent(db, agent_id, include_deleted=True)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    agent = await agent_service.update_agent(db, agent, body)
    await db.refresh(agent)
    return AgentResponse.from_orm_agent(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "delete")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    await agent_service.delete_agent(db, agent)
    return None

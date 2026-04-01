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
    """Batch check agent readiness (has ready pods) for sidebar display."""
    import asyncio
    from app.services import controller_client, redis_service

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
            agent = await agent_service.get_agent(db, uuid.UUID(aid))
            if not agent or not agent.deployment_active or not agent.namespace:
                result = "offline"
            else:
                status_info = await controller_client.get_deployment_status(agent.namespace)
                ready = status_info.get("ready_replicas", 0)
                result = "ready" if ready and ready >= 1 else "offline"
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
    """Get agent details."""
    agent = await agent_service.get_agent(db, agent_id)
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
    """Update agent configuration."""
    agent = await agent_service.get_agent(db, agent_id)
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


# ── Agent Deployment Management ──────────────────────────────


@router.post("/{agent_id}/activate")
async def activate_agent(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually activate an agent's Deployment (spawn pods)."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    try:
        await agent_service.activate_agent(db, agent)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "activated", "deployment_active": True}


@router.post("/{agent_id}/deactivate")
async def deactivate_agent(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually deactivate an agent's Deployment (scale to 0)."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    await agent_service.deactivate_agent(db, agent)
    return {"status": "deactivated", "deployment_active": False}


@router.get("/{agent_id}/deployment")
async def get_deployment_status(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get Deployment status for an agent."""
    from app.services import controller_client

    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "view")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    if agent.namespace:
        status_info = await controller_client.get_deployment_status(agent.namespace)
    else:
        status_info = {"replicas": 0, "ready_replicas": 0, "updated_replicas": 0}

    return {
        "deployment_active": agent.deployment_active,
        "pod_strategy": agent.pod_strategy,
        "min_pods": agent.min_pods,
        "max_pods": agent.max_pods,
        **status_info,
    }


@router.post("/{agent_id}/deploy")
async def deploy_agent(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a rolling restart to apply config changes."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    await agent_service.deploy_agent(db, agent)
    return {"status": "deploying"}

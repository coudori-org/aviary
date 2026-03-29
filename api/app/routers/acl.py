import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AgentACL, User
from app.db.session import get_db
from app.schemas.acl import ACLCreate, ACLListResponse, ACLResponse, ACLUpdate
from app.services import acl_service, agent_service

router = APIRouter()


@router.get("/{agent_id}/acl", response_model=ACLListResponse)
async def list_acl(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ACL entries for an agent."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "view")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    result = await db.execute(select(AgentACL).where(AgentACL.agent_id == agent_id))
    acl_entries = result.scalars().all()
    return ACLListResponse(items=[ACLResponse.from_orm_acl(a) for a in acl_entries])


@router.post("/{agent_id}/acl", response_model=ACLResponse, status_code=status.HTTP_201_CREATED)
async def create_acl(
    agent_id: uuid.UUID,
    body: ACLCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant access to a user or team."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "manage_acl")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    if not body.user_id and not body.team_id:
        raise HTTPException(status_code=400, detail="Either user_id or team_id is required")
    if body.user_id and body.team_id:
        raise HTTPException(status_code=400, detail="Only one of user_id or team_id allowed")

    acl = AgentACL(
        agent_id=agent_id,
        user_id=uuid.UUID(body.user_id) if body.user_id else None,
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        role=body.role,
    )
    db.add(acl)
    try:
        await db.flush()
    except Exception as e:
        raise HTTPException(status_code=409, detail="ACL entry already exists") from e

    return ACLResponse.from_orm_acl(acl)


@router.put("/{agent_id}/acl/{acl_id}", response_model=ACLResponse)
async def update_acl(
    agent_id: uuid.UUID,
    acl_id: uuid.UUID,
    body: ACLUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an ACL entry's role."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "manage_acl")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    result = await db.execute(
        select(AgentACL).where(AgentACL.id == acl_id, AgentACL.agent_id == agent_id)
    )
    acl = result.scalar_one_or_none()
    if not acl:
        raise HTTPException(status_code=404, detail="ACL entry not found")

    acl.role = body.role
    await db.flush()
    return ACLResponse.from_orm_acl(acl)


@router.delete("/{agent_id}/acl/{acl_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_acl(
    agent_id: uuid.UUID,
    acl_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke access."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "manage_acl")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    result = await db.execute(
        select(AgentACL).where(AgentACL.id == acl_id, AgentACL.agent_id == agent_id)
    )
    acl = result.scalar_one_or_none()
    if not acl:
        raise HTTPException(status_code=404, detail="ACL entry not found")

    await db.delete(acl)
    return None

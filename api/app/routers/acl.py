import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_agent_permission
from app.db.models import Agent, AgentACL
from app.db.session import get_db
from app.schemas.acl import ACLCreate, ACLListResponse, ACLResponse, ACLUpdate

router = APIRouter()


@router.get("/{agent_id}/acl", response_model=ACLListResponse)
async def list_acl(
    agent: Agent = Depends(require_agent_permission("view")),
    db: AsyncSession = Depends(get_db),
):
    """List ACL entries for an agent."""
    result = await db.execute(select(AgentACL).where(AgentACL.agent_id == agent.id))
    acl_entries = result.scalars().all()
    return ACLListResponse(items=[ACLResponse.from_orm_acl(a) for a in acl_entries])


@router.post("/{agent_id}/acl", response_model=ACLResponse, status_code=status.HTTP_201_CREATED)
async def create_acl(
    body: ACLCreate,
    agent: Agent = Depends(require_agent_permission("manage_acl")),
    db: AsyncSession = Depends(get_db),
):
    """Grant access to a user or team."""
    if not body.user_id and not body.team_id:
        raise HTTPException(status_code=400, detail="Either user_id or team_id is required")
    if body.user_id and body.team_id:
        raise HTTPException(status_code=400, detail="Only one of user_id or team_id allowed")

    acl = AgentACL(
        agent_id=agent.id,
        user_id=uuid.UUID(body.user_id) if body.user_id else None,
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        role=body.role,
    )
    db.add(acl)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="ACL entry already exists") from e

    return ACLResponse.from_orm_acl(acl)


@router.put("/{agent_id}/acl/{acl_id}", response_model=ACLResponse)
async def update_acl(
    acl_id: uuid.UUID,
    body: ACLUpdate,
    agent: Agent = Depends(require_agent_permission("manage_acl")),
    db: AsyncSession = Depends(get_db),
):
    """Update an ACL entry's role."""
    result = await db.execute(
        select(AgentACL).where(AgentACL.id == acl_id, AgentACL.agent_id == agent.id)
    )
    acl = result.scalar_one_or_none()
    if not acl:
        raise HTTPException(status_code=404, detail="ACL entry not found")

    acl.role = body.role
    await db.flush()
    return ACLResponse.from_orm_acl(acl)


@router.delete("/{agent_id}/acl/{acl_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_acl(
    acl_id: uuid.UUID,
    agent: Agent = Depends(require_agent_permission("manage_acl")),
    db: AsyncSession = Depends(get_db),
):
    """Revoke access."""
    result = await db.execute(
        select(AgentACL).where(AgentACL.id == acl_id, AgentACL.agent_id == agent.id)
    )
    acl = result.scalar_one_or_none()
    if not acl:
        raise HTTPException(status_code=404, detail="ACL entry not found")

    await db.delete(acl)
    return None

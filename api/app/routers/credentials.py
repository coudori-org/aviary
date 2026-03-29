import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import AgentCredential, User
from app.db.session import get_db
from app.services import acl_service, agent_service, vault_service

router = APIRouter()


class CredentialCreate(BaseModel):
    name: str
    value: str
    description: str | None = None


class CredentialResponse(BaseModel):
    id: str
    agent_id: str
    name: str
    vault_path: str
    description: str | None = None

    @classmethod
    def from_orm(cls, cred: AgentCredential) -> "CredentialResponse":
        return cls(
            id=str(cred.id),
            agent_id=str(cred.agent_id),
            name=cred.name,
            vault_path=cred.vault_path,
            description=cred.description,
        )


class CredentialListResponse(BaseModel):
    items: list[CredentialResponse]


@router.get("/{agent_id}/credentials", response_model=CredentialListResponse)
async def list_credentials(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List credential names for an agent (values are NOT returned)."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    result = await db.execute(
        select(AgentCredential).where(AgentCredential.agent_id == agent_id)
    )
    creds = result.scalars().all()
    return CredentialListResponse(items=[CredentialResponse.from_orm(c) for c in creds])


@router.post(
    "/{agent_id}/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_credential(
    agent_id: uuid.UUID,
    body: CredentialCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a credential — value is stored in Vault, only name/path stored in DB."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    vault_path = f"aviary/agents/{agent_id}/credentials/{body.name}"

    # Store secret in Vault
    try:
        await vault_service.write_secret(vault_path, {"value": body.value})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Vault error: {e}") from e

    # Store reference in DB
    cred = AgentCredential(
        agent_id=agent_id,
        name=body.name,
        vault_path=vault_path,
        description=body.description,
    )
    db.add(cred)
    try:
        await db.flush()
    except Exception as e:
        raise HTTPException(status_code=409, detail="Credential name already exists") from e

    return CredentialResponse.from_orm(cred)


@router.delete("/{agent_id}/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    agent_id: uuid.UUID,
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a credential from both Vault and DB."""
    agent = await agent_service.get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await acl_service.check_agent_permission(db, user, agent, "edit_config")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    result = await db.execute(
        select(AgentCredential).where(
            AgentCredential.agent_id == agent_id,
            AgentCredential.name == name,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Delete from Vault
    try:
        await vault_service.delete_secret(cred.vault_path)
    except Exception:
        pass  # Best effort — DB record removal is more important

    await db.delete(cred)
    return None

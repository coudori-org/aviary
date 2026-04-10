import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_agent_permission
from app.db.models import Agent, AgentCredential
from app.db.session import get_db
from app.services import vault_service

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
    agent: Agent = Depends(require_agent_permission("edit_config")),
    db: AsyncSession = Depends(get_db),
):
    """List credential names for an agent (values are NOT returned)."""
    result = await db.execute(
        select(AgentCredential).where(AgentCredential.agent_id == agent.id)
    )
    creds = result.scalars().all()
    return CredentialListResponse(items=[CredentialResponse.from_orm(c) for c in creds])


@router.post(
    "/{agent_id}/credentials",
    response_model=CredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_credential(
    body: CredentialCreate,
    agent: Agent = Depends(require_agent_permission("edit_config")),
    db: AsyncSession = Depends(get_db),
):
    """Add a credential — value is stored in Vault, only name/path stored in DB."""
    vault_path = f"aviary/agents/{agent.id}/credentials/{body.name}"

    try:
        await vault_service.write_secret(vault_path, {"value": body.value})
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Vault error: {e}") from e

    cred = AgentCredential(
        agent_id=agent.id,
        name=body.name,
        vault_path=vault_path,
        description=body.description,
    )
    db.add(cred)
    try:
        await db.flush()
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="Credential name already exists") from e

    return CredentialResponse.from_orm(cred)


@router.delete("/{agent_id}/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    name: str,
    agent: Agent = Depends(require_agent_permission("edit_config")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a credential from both Vault and DB."""
    result = await db.execute(
        select(AgentCredential).where(
            AgentCredential.agent_id == agent.id,
            AgentCredential.name == name,
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="Credential not found")

    try:
        await vault_service.delete_secret(cred.vault_path)
    except httpx.HTTPError:  # Best-effort: DB record removal is more important
        pass

    await db.delete(cred)
    return None

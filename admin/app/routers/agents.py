"""Agent management — no ACL, full access."""

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# Local schema copy: admin's container doesn't import the API package.
# Shape mirrors the API exactly so shared JS/TS clients can consume both.

def _to_str(v):
    return str(v) if isinstance(v, uuid.UUID) else v


_UuidStr = Annotated[str, BeforeValidator(_to_str)]
_MODEL_CONFIG_ALIAS = {"alias": "model_config"}


class AgentResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True, populate_by_name=True, protected_namespaces=(),
    )

    id: _UuidStr
    name: str
    slug: str
    description: str | None = None
    owner_id: _UuidStr
    instruction: str
    model_config_json: dict = Field(**_MODEL_CONFIG_ALIAS)
    tools: list
    mcp_servers: list
    icon: str | None = None
    runtime_endpoint: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class AgentUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    model_config_json: dict | None = Field(None, **_MODEL_CONFIG_ALIAS)
    tools: list[str] | None = None
    mcp_servers: list | None = None
    icon: str | None = None
    runtime_endpoint: str | None = None


@router.get("", response_model=AgentListResponse)
async def list_agents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(
        select(func.count()).select_from(Agent)
    )).scalar() or 0
    agents = (await db.execute(
        select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )).scalars().all()
    return AgentListResponse(
        items=[AgentResponse.model_validate(a) for a in agents], total=total,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Empty string clears runtime_endpoint to revert to the default runtime.
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "runtime_endpoint" and value == "":
            value = None
        setattr(agent, field, value)

    await db.flush()
    await db.refresh(agent)
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.flush()
    return None

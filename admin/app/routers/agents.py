"""Agent management — list, detail, update, delete (no ACL, full access)."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from app.db import get_db
from app.services import agent_lifecycle

logger = logging.getLogger(__name__)

router = APIRouter()


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    slug: str
    description: str | None = None
    owner_id: str
    instruction: str
    model_config_data: dict
    tools: list
    mcp_servers: list
    visibility: str
    category: str | None = None
    icon: str | None = None
    policy_id: str | None = None
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentResponse":
        return cls(
            id=str(agent.id),
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            owner_id=str(agent.owner_id),
            instruction=agent.instruction,
            model_config_data=agent.model_config_json,
            tools=agent.tools,
            mcp_servers=agent.mcp_servers,
            visibility=agent.visibility,
            category=agent.category,
            icon=agent.icon,
            policy_id=str(agent.policy_id) if agent.policy_id else None,
            status=agent.status,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class AgentUpdateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    name: str | None = None
    description: str | None = None
    instruction: str | None = None
    model_config_data: dict | None = Field(None, alias="model_config")
    tools: list[str] | None = None
    mcp_servers: list | None = None
    visibility: str | None = None
    category: str | None = None
    icon: str | None = None


@router.get("", response_model=AgentListResponse)
async def list_agents(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(select(func.count()).select_from(Agent))
    total = count_result.scalar() or 0

    result = await db.execute(
        select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(limit)
    )
    agents = result.scalars().all()

    return AgentListResponse(
        items=[AgentResponse.from_agent(a) for a in agents],
        total=total,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.from_agent(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Apply only fields the caller explicitly set; map model_config_data → model_config_json.
    field_map = {"model_config_data": "model_config_json"}
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, field_map.get(field, field), value)

    await db.flush()
    await db.refresh(agent)
    return AgentResponse.from_agent(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Hard-delete an agent and all its K8s resources."""
    agent = await agent_lifecycle.find_agent_or_none(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        await agent_lifecycle.delete_agent(db, agent)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Delete failed: {e}") from e
    return None

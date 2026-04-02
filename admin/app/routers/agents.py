"""Agent management — list, detail, update, delete (no ACL, full access)."""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from app.db import get_db
from app.services import controller_client

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
    policy: dict
    visibility: str
    category: str | None = None
    icon: str | None = None
    pod_strategy: str
    min_pods: int
    max_pods: int
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
            policy=agent.policy,
            visibility=agent.visibility,
            category=agent.category,
            icon=agent.icon,
            pod_strategy=agent.pod_strategy,
            min_pods=agent.min_pods,
            max_pods=agent.max_pods,
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
    """List all agents (no ACL filtering)."""
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
    """Get agent detail including infrastructure fields."""
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
    """Update agent config and sync to K8s."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.name is not None:
        agent.name = body.name
    if body.description is not None:
        agent.description = body.description
    if body.instruction is not None:
        agent.instruction = body.instruction
    if body.model_config_data is not None:
        agent.model_config_json = body.model_config_data
    if body.tools is not None:
        agent.tools = body.tools
    if body.mcp_servers is not None:
        agent.mcp_servers = body.mcp_servers
    if body.visibility is not None:
        agent.visibility = body.visibility
    if body.category is not None:
        agent.category = body.category
    if body.icon is not None:
        agent.icon = body.icon

    await db.flush()

    # Sync to K8s
    ns = f"agent-{agent.id}"
    try:
        await controller_client.update_namespace_config(
            namespace=ns,
            instruction=agent.instruction,
            tools=agent.tools,
            policy=agent.policy,
            mcp_servers=agent.mcp_servers,
        )
    except Exception:
        logger.warning("K8s config sync failed for agent %s", agent.id, exc_info=True)

    await db.refresh(agent)
    return AgentResponse.from_agent(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Hard-delete an agent and all its K8s resources."""
    from aviary_shared.db.models import Session as SessionModel
    from sqlalchemy import delete

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Clean up K8s resources
    ns = f"agent-{agent.id}"
    try:
        await controller_client.delete_deployment(ns)
    except Exception:
        pass
    try:
        await controller_client.delete_namespace(str(agent.id))
    except Exception:
        pass

    # Delete all sessions, then the agent
    await db.execute(delete(SessionModel).where(SessionModel.agent_id == agent.id))
    await db.delete(agent)
    await db.flush()
    return None

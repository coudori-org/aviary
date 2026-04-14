"""Policy management — resource limits + scaling bounds + SA binding sync."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aviary_shared.db.models import Agent, Policy
from app.db import get_db
from app.services import agent_lifecycle

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_policy_for_agent(db: AsyncSession, agent_id: uuid.UUID) -> tuple[Agent, Policy]:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id).options(
            selectinload(Agent.policy), selectinload(Agent.service_account),
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not agent.policy:
        policy = Policy()
        db.add(policy)
        await db.flush()
        agent.policy_id = policy.id
        await db.flush()
        agent.policy = policy
    return agent, agent.policy


@router.get("/{agent_id}/policy")
async def get_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent, policy = await _get_policy_for_agent(db, agent_id)
    return {
        "agent_id": str(agent.id),
        "policy": policy.policy_rules,
        "min_pods": policy.min_pods,
        "max_pods": policy.max_pods,
        "service_account_id": str(agent.service_account_id) if agent.service_account_id else None,
    }


class PolicyUpdateRequest(BaseModel):
    policy: dict | None = None
    min_pods: int | None = None
    max_pods: int | None = None
    service_account_id: uuid.UUID | None = None


@router.put("/{agent_id}/policy")
async def update_policy(
    agent_id: uuid.UUID,
    body: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    agent, policy = await _get_policy_for_agent(db, agent_id)

    if body.policy is not None:
        policy.policy_rules = body.policy
    if body.min_pods is not None:
        policy.min_pods = body.min_pods
    if body.max_pods is not None:
        policy.max_pods = body.max_pods
    # Only touch SA binding when caller explicitly includes the field (null = clear).
    if "service_account_id" in body.model_fields_set:
        agent.service_account_id = body.service_account_id
        await db.flush()
        await db.refresh(agent, attribute_names=["service_account"])

    await db.flush()

    identity_synced = True
    sync_error: str | None = None
    try:
        await agent_lifecycle.sync_identity(agent)
    except httpx.HTTPError as e:
        identity_synced = False
        sync_error = str(e)

    return {
        "agent_id": str(agent.id),
        "policy": policy.policy_rules,
        "min_pods": policy.min_pods,
        "max_pods": policy.max_pods,
        "service_account_id": str(agent.service_account_id) if agent.service_account_id else None,
        "identity_synced": identity_synced,
        "sync_error": sync_error,
    }


@router.post("/{agent_id}/policy/sync")
async def force_sync_policy(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent, _ = await _get_policy_for_agent(db, agent_id)
    try:
        await agent_lifecycle.sync_identity(agent)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Identity sync failed: {e}") from e
    return {"agent_id": str(agent.id), "synced": {"identity": True}}

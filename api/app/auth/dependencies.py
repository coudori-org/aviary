"""Auth dependencies — owner-only access model.

Broader RBAC (teams, sharing, roles) will return when we redesign access
control. For now, an agent/workflow/session is only accessible to its
owner/creator.
"""

import uuid

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import TokenClaims, validate_token
from app.auth.session_store import (
    SESSION_COOKIE_NAME,
    SessionData,
    get_fresh_session,
)
from app.db.models import Agent, User, Workflow
from app.db.session import get_db


async def _upsert_user(db: AsyncSession, claims: TokenClaims) -> User:
    result = await db.execute(select(User).where(User.external_id == claims.sub))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            external_id=claims.sub,
            email=claims.email,
            display_name=claims.display_name,
        )
        db.add(user)
        await db.flush()
    elif user.email != claims.email or user.display_name != claims.display_name:
        user.email = claims.email
        user.display_name = claims.display_name
        await db.flush()

    return user


async def get_session_data(
    aviary_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> SessionData:
    if not aviary_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    data = await get_fresh_session(aviary_session)
    if data is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return data


async def get_current_user(
    session: SessionData = Depends(get_session_data),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        claims = await validate_token(session.id_token or "")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    return await _upsert_user(db, claims)


def require_agent_owner():
    """Fetch agent by path `agent_id` and 403 unless the caller owns it."""
    async def dependency(
        agent_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Agent:
        agent = (await db.execute(
            select(Agent).where(Agent.id == agent_id)
        )).scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Not the owner of this agent")
        return agent

    return dependency


def require_workflow_owner():
    # Eager-load versions so response serialization can read
    # `Workflow.current_version` without a second query per request.
    from sqlalchemy.orm import selectinload

    async def dependency(
        workflow_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Workflow:
        workflow = (await db.execute(
            select(Workflow)
            .options(selectinload(Workflow.versions))
            .where(Workflow.id == workflow_id)
        )).scalar_one_or_none()
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        if workflow.owner_id != user.id:
            raise HTTPException(status_code=403, detail="Not the owner of this workflow")
        return workflow

    return dependency

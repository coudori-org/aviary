"""JWT validation and ACL enforcement for the agent supervisor.

Uses the shared OIDC validator and ACL module. Every agent-centric API call
requires a valid user token with "chat" permission on the target agent.
"""

import logging
import uuid

from fastapi import HTTPException

from aviary_shared.auth.oidc import OIDCValidator, TokenClaims
from aviary_shared.auth.acl import resolve_agent_role_by_id, has_permission

from app.config import settings
from app.db import async_session_factory

logger = logging.getLogger(__name__)

# Singleton OIDC validator for this service
_validator = OIDCValidator(
    issuer=settings.oidc_issuer,
    internal_issuer=settings.oidc_internal_issuer,
    audience=settings.oidc_audience,
)


async def init_oidc() -> None:
    """Pre-fetch OIDC config on startup."""
    await _validator.init()


async def validate_user_token(token: str) -> TokenClaims:
    """Validate a JWT and return claims. Raises HTTPException on failure."""
    try:
        return await _validator.validate_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


async def enforce_agent_permission(
    user_token: str | None, agent_id: str, permission: str = "chat"
) -> TokenClaims:
    """Validate user token and check ACL for the target agent.

    Raises HTTPException(401) if token is missing/invalid,
    HTTPException(403) if user lacks the required permission.
    """
    if not user_token:
        raise HTTPException(status_code=401, detail="Missing user token")

    claims = await validate_user_token(user_token)

    async with async_session_factory() as db:
        # Look up user by external_id (sub claim) to get internal user_id
        from sqlalchemy import select
        from aviary_shared.db.models import User

        result = await db.execute(
            select(User).where(User.external_id == claims.sub)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        try:
            agent_uuid = uuid.UUID(agent_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid agent_id format")

        role = await resolve_agent_role_by_id(db, user.id, agent_uuid)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"User lacks '{permission}' permission on agent {agent_id}",
            )

    return claims

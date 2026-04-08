from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import TokenClaims, validate_token
from app.db.models import User
from app.db.session import get_db
from app.services.team_sync_service import sync_user_teams

security = HTTPBearer()


async def _upsert_user(db: AsyncSession, claims: TokenClaims) -> User:
    """Create user on first login or update existing user info."""
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
    else:
        user.email = claims.email
        user.display_name = claims.display_name
        await db.flush()

    # Sync OIDC groups → Aviary teams
    if claims.groups is not None:
        await sync_user_teams(db, user.id, claims.groups)

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer token, upsert user, return User model."""
    try:
        claims = await validate_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    return await _upsert_user(db, claims)


async def get_raw_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Return the raw Bearer token string for forwarding to downstream services."""
    return credentials.credentials

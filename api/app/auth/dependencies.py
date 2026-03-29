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

    is_admin = "platform_admin" in claims.roles

    if user is None:
        user = User(
            external_id=claims.sub,
            email=claims.email,
            display_name=claims.display_name,
            is_platform_admin=is_admin,
        )
        db.add(user)
        await db.flush()
    else:
        user.email = claims.email
        user.display_name = claims.display_name
        user.is_platform_admin = is_admin
        await db.flush()

    # Sync OIDC groups → AgentBox teams
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


async def require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Require the user to have platform_admin role."""
    if not user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )
    return user

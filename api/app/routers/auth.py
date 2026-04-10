import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.oidc import exchange_code, get_oidc_config, refresh_tokens, to_public_url, validate_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.common import (
    AuthConfigResponse,
    TokenExchangeRequest,
    TokenExchangeResponse,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserResponse,
)

router = APIRouter()


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    """Return OIDC configuration for the frontend."""
    config = await get_oidc_config()
    # Discovery doc URLs may contain internal hostnames (e.g. keycloak:8080).
    # Rewrite them to public URLs (localhost:8080) for the browser.
    return AuthConfigResponse(
        issuer=to_public_url(config["issuer"]),
        client_id="aviary-web",
        authorization_endpoint=to_public_url(config["authorization_endpoint"]),
        token_endpoint=to_public_url(config["token_endpoint"]),
        end_session_endpoint=to_public_url(config.get("end_session_endpoint", "")),
    )


@router.post("/callback", response_model=TokenExchangeResponse)
async def auth_callback(body: TokenExchangeRequest, db: AsyncSession = Depends(get_db)):
    """Exchange authorization code for tokens and upsert user."""
    try:
        token_data = await exchange_code(body.code, body.redirect_uri, body.code_verifier)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {e}",
        ) from e

    access_token = token_data["access_token"]

    # Validate the access token and upsert user
    try:
        claims = await validate_token(access_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    from app.auth.dependencies import _upsert_user

    user = await _upsert_user(db, claims)

    return TokenExchangeResponse(
        access_token=access_token,
        refresh_token=token_data.get("refresh_token"),
        id_token=token_data.get("id_token"),
        token_type="Bearer",
        expires_in=token_data.get("expires_in", 300),
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
async def auth_refresh(body: TokenRefreshRequest):
    """Exchange a refresh token for a new access token."""
    try:
        token_data = await refresh_tokens(body.refresh_token)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token refresh failed: {e}",
        ) from e

    return TokenRefreshResponse(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        id_token=token_data.get("id_token"),
        token_type="Bearer",
        expires_in=token_data.get("expires_in", 300),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    """Logout endpoint. Client-side token cleanup; server is stateless."""
    return None

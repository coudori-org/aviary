from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import _upsert_user, get_current_user
from app.auth.oidc import exchange_code, get_oidc_config, to_public_url, validate_token
from app.auth.session_store import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session,
    delete_session,
    peek_session,
)
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.schemas.common import (
    AuthConfigResponse,
    LogoutRequest,
    LogoutResponse,
    PreferencesUpdateRequest,
    TokenExchangeRequest,
    UserResponse,
)

router = APIRouter()

_COOKIE_KW = dict(
    key=SESSION_COOKIE_NAME,
    httponly=True,
    samesite="lax",
    path="/",
    max_age=SESSION_TTL_SECONDS,
)


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(value=session_id, secure=settings.cookie_secure, **_COOKIE_KW)


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config():
    config = await get_oidc_config()
    # Discovery URLs come back with the internal hostname (keycloak:8080);
    # the browser needs the public one.
    return AuthConfigResponse(
        issuer=to_public_url(config["issuer"]),
        client_id=settings.oidc_client_id,
        authorization_endpoint=to_public_url(config["authorization_endpoint"]),
        token_endpoint=to_public_url(config["token_endpoint"]),
        end_session_endpoint=to_public_url(config.get("end_session_endpoint", "")),
    )


@router.post("/callback", response_model=UserResponse)
async def auth_callback(
    body: TokenExchangeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    try:
        token_data = await exchange_code(body.code, body.redirect_uri, body.code_verifier)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token exchange failed: {e}",
        ) from e

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    # No refresh token = we can't keep the session alive past the access
    # token's lifetime, which defeats the whole design. Hard fail.
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OIDC server did not return a refresh token",
        )

    try:
        claims = await validate_token(access_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e

    user = await _upsert_user(db, claims)

    session_id = await create_session(
        user_external_id=claims.sub,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=token_data.get("id_token"),
        expires_in=token_data.get("expires_in", 300),
    )
    _set_session_cookie(response, session_id)

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.patch("/me/preferences", response_model=UserResponse)
async def update_preferences(
    body: PreferencesUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # SQLAlchemy doesn't track in-place mutations on JSONB; reassign.
    merged = {**(user.preferences or {}), **body.preferences}
    user.preferences = merged
    await db.commit()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    body: LogoutRequest | None = None,
    aviary_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    """Clear the server session and return the IdP's RP-initiated-logout URL.

    The browser then navigates there to end the SSO session. We build the
    URL server-side so we can include `id_token_hint` (required by Okta,
    recommended by Keycloak post-18). The browser no longer needs to know
    the IdP's exact end_session shape.
    """
    end_session_url = ""

    if aviary_session:
        session_data = await peek_session(aviary_session)
        id_token_hint = session_data.id_token if session_data else None

        try:
            config = await get_oidc_config()
            end_session_endpoint = config.get("end_session_endpoint")
        except Exception:
            end_session_endpoint = None

        if end_session_endpoint and body and body.post_logout_redirect_uri:
            params: dict[str, str] = {
                "post_logout_redirect_uri": body.post_logout_redirect_uri,
            }
            if id_token_hint:
                params["id_token_hint"] = id_token_hint
            else:
                # Keycloak 18+ accepts client_id as a fallback when the
                # id_token is unavailable; Okta rejects this — but in
                # that case the user has no active SSO session anyway.
                params["client_id"] = settings.oidc_client_id
            end_session_url = (
                to_public_url(end_session_endpoint) + "?" + urlencode(params)
            )

        await delete_session(aviary_session)

    _clear_session_cookie(response)
    return LogoutResponse(end_session_url=end_session_url)

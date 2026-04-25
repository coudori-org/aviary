"""OIDC auth — thin wrapper over the shared validator.

Provider-agnostic: `aviary_shared.auth.build_oidc_validator` reads
`settings.oidc_provider` and plugs in the right ClaimMapper. Switching
IdP = flip `OIDC_PROVIDER` + point the issuer at the new IdP.
"""

import httpx

from aviary_shared.auth import build_oidc_validator
from aviary_shared.auth.oidc import TokenClaims  # noqa: F401 — re-exported

from app.config import settings

_validator = build_oidc_validator(settings)


async def init_oidc() -> None:
    """Initialize OIDC on startup: fetch discovery doc and JWKS."""
    await _validator.init()


async def validate_token(token: str) -> TokenClaims:
    """Validate a JWT access/ID token and extract claims."""
    return await _validator.validate_token(token)


async def get_oidc_config() -> dict:
    """Return cached OIDC configuration, fetching if needed."""
    return await _validator.get_oidc_config()


async def get_jwks() -> dict:
    """Return cached JWKS, refreshing if expired."""
    return await _validator.get_jwks()


def to_public_url(url: str) -> str:
    """Rewrite an internal URL back to the public-facing URL (for browser use)."""
    return _validator.to_public_url(url)


def _rewrite_url(url: str) -> str:
    """Rewrite a public-facing URL to the internal URL for container-to-container access."""
    return _validator._rewrite_url(url)


async def refresh_tokens(refresh_token: str) -> dict:
    """Exchange a refresh token for new tokens via the OIDC token endpoint."""
    config = await get_oidc_config()
    token_endpoint = _rewrite_url(config["token_endpoint"])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.oidc_client_id,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


async def exchange_code(code: str, redirect_uri: str, code_verifier: str) -> dict:
    """Exchange an authorization code for tokens via the OIDC token endpoint."""
    config = await get_oidc_config()
    token_endpoint = _rewrite_url(config["token_endpoint"])

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.oidc_client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

"""OIDC auth — thin wrapper over shared OIDCValidator.

Keeps the same public API (module-level functions) used by the API server,
but delegates all JWT logic to aviary_shared.auth.oidc.
"""

from aviary_shared.auth.oidc import OIDCValidator, TokenClaims  # noqa: F401

from app.config import settings

# Singleton validator for this service
_validator = OIDCValidator(
    issuer=settings.oidc_issuer,
    internal_issuer=settings.oidc_internal_issuer,
    audience=settings.oidc_audience,
)


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

    import httpx

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

    import httpx

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

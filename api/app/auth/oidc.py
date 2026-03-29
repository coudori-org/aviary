import time
from dataclasses import dataclass, field

import httpx
from jose import JWTError, jwt

from app.config import settings

# OIDC discovery and JWKS cache
_oidc_config: dict | None = None
_jwks: dict | None = None
_jwks_fetched_at: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour


@dataclass
class TokenClaims:
    sub: str
    email: str
    display_name: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)


def _internal_issuer() -> str:
    """Return the internal URL for fetching OIDC metadata (container-to-container).

    Tokens issued by Keycloak contain iss=http://localhost:8080/... (browser URL),
    but the API container must reach Keycloak at http://keycloak:8080/... .
    oidc_internal_issuer is the fetch URL; oidc_issuer is used for token validation.
    """
    return settings.oidc_internal_issuer or settings.oidc_issuer


async def _fetch_oidc_config() -> dict:
    """Fetch OIDC discovery document from the issuer."""
    url = f"{_internal_issuer()}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()


async def get_oidc_config() -> dict:
    """Return cached OIDC configuration, fetching if needed."""
    global _oidc_config
    if _oidc_config is None:
        _oidc_config = await _fetch_oidc_config()
    return _oidc_config


async def _fetch_jwks(jwks_uri: str) -> dict:
    """Fetch JWKS from the OIDC provider."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(jwks_uri, timeout=10)
        resp.raise_for_status()
        return resp.json()


def _rewrite_url(url: str) -> str:
    """Rewrite a public-facing URL to the internal URL for container-to-container access."""
    internal = _internal_issuer()
    public = settings.oidc_issuer
    if internal != public and url.startswith(public):
        return internal + url[len(public):]
    return url


def to_public_url(url: str) -> str:
    """Rewrite an internal URL back to the public-facing URL (for browser use)."""
    internal = _internal_issuer()
    public = settings.oidc_issuer
    if internal != public and url.startswith(internal):
        return public + url[len(internal):]
    return url


async def get_jwks() -> dict:
    """Return cached JWKS, refreshing if expired."""
    global _jwks, _jwks_fetched_at
    now = time.time()
    if _jwks is None or (now - _jwks_fetched_at) > _JWKS_CACHE_TTL:
        config = await get_oidc_config()
        jwks_uri = _rewrite_url(config["jwks_uri"])
        _jwks = await _fetch_jwks(jwks_uri)
        _jwks_fetched_at = now
    return _jwks


async def init_oidc() -> None:
    """Initialize OIDC on startup: fetch discovery doc and JWKS."""
    global _oidc_config, _jwks, _jwks_fetched_at
    try:
        _oidc_config = await _fetch_oidc_config()
        _jwks = await _fetch_jwks(_oidc_config["jwks_uri"])
        _jwks_fetched_at = time.time()
    except Exception:
        # OIDC provider may not be ready yet during local dev startup.
        # Will retry on first request.
        _oidc_config = None
        _jwks = None


async def validate_token(token: str) -> TokenClaims:
    """Validate a JWT access/ID token and extract claims."""
    jwks = await get_jwks()

    try:
        # Decode header to get kid
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise ValueError(f"Invalid token header: {e}") from e

    # Find matching key
    kid = unverified_header.get("kid")
    rsa_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            rsa_key = key
            break

    if rsa_key is None:
        # Key not found — try refreshing JWKS (key rotation)
        global _jwks_fetched_at
        _jwks_fetched_at = 0
        jwks = await get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break
        if rsa_key is None:
            raise ValueError("Token signing key not found in JWKS")

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"verify_aud": settings.oidc_audience is not None},
        )
    except JWTError as e:
        raise ValueError(f"Token validation failed: {e}") from e

    sub = payload.get("sub")
    email = payload.get("email", "")
    display_name = payload.get("name") or payload.get("preferred_username") or email

    # Extract roles from realm_roles claim (Keycloak custom mapper)
    # or from realm_access.roles (Keycloak default)
    roles: list[str] = []
    if "realm_roles" in payload:
        roles = payload["realm_roles"]
    elif "realm_access" in payload:
        roles = payload.get("realm_access", {}).get("roles", [])

    # Extract groups from 'groups' claim (Keycloak group membership mapper)
    # Keycloak returns group paths like "/engineering" — strip leading slash
    raw_groups: list[str] = payload.get("groups", [])
    groups = [g.lstrip("/") for g in raw_groups if g]

    if not sub:
        raise ValueError("Token missing 'sub' claim")

    return TokenClaims(sub=sub, email=email, display_name=display_name, roles=roles, groups=groups)


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

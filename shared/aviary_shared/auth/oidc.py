"""Shared OIDC JWT validation.

Parameterized — no dependency on service-specific config.
Each service creates an OIDCValidator instance with its own OIDC settings.
"""

import time
from dataclasses import dataclass, field

import httpx
from jose import JWTError, jwt


@dataclass
class TokenClaims:
    sub: str
    email: str
    display_name: str
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)


class OIDCValidator:
    """Stateful OIDC validator with JWKS caching."""

    def __init__(
        self,
        issuer: str,
        internal_issuer: str | None = None,
        audience: str | None = None,
        jwks_cache_ttl: int = 3600,
    ):
        self.issuer = issuer
        self.internal_issuer = internal_issuer or issuer
        self.audience = audience
        self._jwks_cache_ttl = jwks_cache_ttl

        self._oidc_config: dict | None = None
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0

    def _rewrite_url(self, url: str) -> str:
        """Rewrite a public-facing URL to the internal URL for container-to-container access."""
        if self.internal_issuer != self.issuer and url.startswith(self.issuer):
            return self.internal_issuer + url[len(self.issuer) :]
        return url

    def to_public_url(self, url: str) -> str:
        """Rewrite an internal URL back to the public-facing URL (for browser use)."""
        if self.internal_issuer != self.issuer and url.startswith(self.internal_issuer):
            return self.issuer + url[len(self.internal_issuer) :]
        return url

    async def _fetch_oidc_config(self) -> dict:
        url = f"{self.internal_issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()

    async def get_oidc_config(self) -> dict:
        if self._oidc_config is None:
            self._oidc_config = await self._fetch_oidc_config()
        return self._oidc_config

    async def _fetch_jwks(self, jwks_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_uri, timeout=10)
            resp.raise_for_status()
            return resp.json()

    async def get_jwks(self) -> dict:
        now = time.time()
        if self._jwks is None or (now - self._jwks_fetched_at) > self._jwks_cache_ttl:
            config = await self.get_oidc_config()
            jwks_uri = self._rewrite_url(config["jwks_uri"])
            self._jwks = await self._fetch_jwks(jwks_uri)
            self._jwks_fetched_at = now
        return self._jwks

    async def init(self) -> None:
        """Pre-fetch OIDC config and JWKS. Best-effort — failures are retried on demand."""
        try:
            self._oidc_config = await self._fetch_oidc_config()
            jwks_uri = self._rewrite_url(self._oidc_config["jwks_uri"])
            self._jwks = await self._fetch_jwks(jwks_uri)
            self._jwks_fetched_at = time.time()
        except Exception:
            self._oidc_config = None
            self._jwks = None

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT access/ID token and extract claims."""
        jwks = await self.get_jwks()

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            raise ValueError(f"Invalid token header: {e}") from e

        kid = unverified_header.get("kid")
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = key
                break

        if rsa_key is None:
            # Key rotation — force JWKS refresh
            self._jwks_fetched_at = 0
            jwks = await self.get_jwks()
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
                issuer=self.issuer,
                audience=self.audience,
                options={"verify_aud": self.audience is not None},
            )
        except JWTError as e:
            raise ValueError(f"Token validation failed: {e}") from e

        sub = payload.get("sub")
        email = payload.get("email", "")
        display_name = payload.get("name") or payload.get("preferred_username") or email

        roles: list[str] = []
        if "realm_roles" in payload:
            roles = payload["realm_roles"]
        elif "realm_access" in payload:
            roles = payload.get("realm_access", {}).get("roles", [])

        raw_groups: list[str] = payload.get("groups", [])
        groups = [g.lstrip("/") for g in raw_groups if g]

        if not sub:
            raise ValueError("Token missing 'sub' claim")

        return TokenClaims(
            sub=sub, email=email, display_name=display_name, roles=roles, groups=groups
        )

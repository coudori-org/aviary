"""Shared OIDC JWT validation.

IdP-agnostic: discovery + JWKS caching + RS256 signature verification. The
IdP-specific bit (how roles/groups/etc. are laid out in the payload) is
delegated to an injected `ClaimMapper` — see `aviary_shared.auth.claims`.

Each service constructs one `OIDCValidator` on startup, wired from its
`IdpSettings`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
from jose import JWTError, jwt

if TYPE_CHECKING:
    from aviary_shared.auth.claims import ClaimMapper


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
        claim_mapper: "ClaimMapper | None" = None,
    ):
        self.issuer = issuer
        self.internal_issuer = internal_issuer or issuer
        self.audience = audience
        self._jwks_cache_ttl = jwks_cache_ttl

        if claim_mapper is None:
            # Defer import to avoid circular-dep churn while keeping the
            # default ergonomic for tests that don't care about provider.
            from aviary_shared.auth.claims import KeycloakClaimMapper
            claim_mapper = KeycloakClaimMapper()
        self._claim_mapper = claim_mapper

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
        except Exception:  # Best-effort: failures are retried on demand
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

        return self._claim_mapper.map(payload)

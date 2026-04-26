from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from jose import JWTError, jwt


@dataclass
class TokenClaims:
    sub: str
    email: str
    display_name: str


def _extract_claims(payload: dict) -> TokenClaims:
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token missing 'sub' claim")
    email = payload.get("email", "")
    display_name = (
        payload.get("name")
        or payload.get("preferred_username")
        or email
        or sub
    )
    return TokenClaims(sub=sub, email=email, display_name=display_name)


class OIDCValidator:
    """OIDC validator with JWKS caching. ``issuer=None`` switches to null
    mode: every ``validate_token`` call returns the dev-user claims."""

    def __init__(
        self,
        issuer: str | None,
        internal_issuer: str | None = None,
        jwks_cache_ttl: int = 3600,
        dev_user_sub: str = "dev-user",
    ):
        self.enabled = bool(issuer)
        self.issuer = issuer or ""
        self.internal_issuer = internal_issuer or self.issuer
        self._jwks_cache_ttl = jwks_cache_ttl

        self._dev_claims = TokenClaims(
            sub=dev_user_sub,
            email=f"{dev_user_sub}@aviary.local",
            display_name="Dev User",
        )

        self._oidc_config: dict | None = None
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0

    @property
    def dev_user_sub(self) -> str:
        return self._dev_claims.sub

    def _rewrite_url(self, url: str) -> str:
        if self.internal_issuer != self.issuer and url.startswith(self.issuer):
            return self.internal_issuer + url[len(self.issuer) :]
        return url

    def to_public_url(self, url: str) -> str:
        if self.internal_issuer != self.issuer and url.startswith(self.internal_issuer):
            return self.issuer + url[len(self.internal_issuer) :]
        return url

    async def _fetch_oidc_config(self) -> dict:
        # Auth0 issuers end with `/`, which the `iss` claim requires verbatim
        url = f"{self.internal_issuer.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()

    async def get_oidc_config(self) -> dict:
        if not self.enabled:
            raise RuntimeError("OIDC is disabled — no discovery document available")
        if self._oidc_config is None:
            self._oidc_config = await self._fetch_oidc_config()
        return self._oidc_config

    async def _fetch_jwks(self, jwks_uri: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(jwks_uri, timeout=10)
            resp.raise_for_status()
            return resp.json()

    async def get_jwks(self) -> dict:
        if not self.enabled:
            raise RuntimeError("OIDC is disabled — no JWKS available")
        now = time.time()
        if self._jwks is None or (now - self._jwks_fetched_at) > self._jwks_cache_ttl:
            config = await self.get_oidc_config()
            jwks_uri = self._rewrite_url(config["jwks_uri"])
            self._jwks = await self._fetch_jwks(jwks_uri)
            self._jwks_fetched_at = now
        return self._jwks

    async def init(self) -> None:
        if not self.enabled:
            return
        try:
            self._oidc_config = await self._fetch_oidc_config()
            jwks_uri = self._rewrite_url(self._oidc_config["jwks_uri"])
            self._jwks = await self._fetch_jwks(jwks_uri)
            self._jwks_fetched_at = time.time()
        except Exception:  # best-effort — retried on demand
            self._oidc_config = None
            self._jwks = None

    async def validate_token(self, token: str) -> TokenClaims:
        if not self.enabled:
            return self._dev_claims

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
            # key rotation — force JWKS refresh once
            self._jwks_fetched_at = 0
            jwks = await self.get_jwks()
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = key
                    break
            if rsa_key is None:
                raise ValueError("Token signing key not found in JWKS")

        # discovery doc's `issuer` is the canonical form a token's `iss`
        # will carry (Auth0 keeps a trailing slash; env URLs may not).
        expected_iss = (self._oidc_config or {}).get("issuer") or self.issuer
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                issuer=expected_iss,
                # at_hash binds id_token to access_token; we don't keep
                # access_token around to verify, and JWKS-signature + iss
                # check already guarantees integrity for our use.
                options={"verify_aud": False, "verify_at_hash": False},
            )
        except JWTError as e:
            raise ValueError(f"Token validation failed: {e}") from e

        return _extract_claims(payload)

"""JWT + JWKS + URL rewrite — shared by the two LiteLLM patches.

LiteLLM's container carries PyJWT (not python-jose), so we can't reuse
``aviary_shared.auth.oidc`` from here — it depends on jose. Keeping this
module self-contained and LiteLLM-local.

JWT sub-validation cache stays: it's perf for hot re-validation, not a
state mirror. Vault credential caching is deliberately NOT done — user
profile changes must reflect immediately on the next call.
"""

from __future__ import annotations

import hashlib
import os
import time

import httpx
import jwt as _pyjwt
from jwt.algorithms import RSAAlgorithm


class JwtValidator:
    """Validates OIDC JWTs against Keycloak JWKS.

    Parameterless constructor picks up ``OIDC_ISSUER`` / ``OIDC_INTERNAL_ISSUER``
    from the environment — both patches share one module-level instance.
    """

    # Minimum seconds between forced refetches on an unknown kid. Prevents a
    # flood of tokens carrying random kids from hammering the IdP.
    _FORCE_REFETCH_COOLDOWN = 5

    def __init__(self, *, jwks_ttl: int = 3600, sub_cache_ttl: int = 1800) -> None:
        self.issuer = os.environ.get("OIDC_ISSUER", "")
        self.internal_issuer = os.environ.get("OIDC_INTERNAL_ISSUER", "") or self.issuer
        self._jwks_ttl = jwks_ttl
        self._sub_cache_ttl = sub_cache_ttl
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0
        self._last_forced_refetch_at: float = 0
        self._sub_cache: dict[str, tuple[str, float]] = {}

    # ---- URL rewrite -----------------------------------------------------

    def rewrite_to_internal(self, url: str) -> str:
        """Rewrite a public-issuer URL to the in-cluster DNS form."""
        if self.internal_issuer != self.issuer and url.startswith(self.issuer):
            return self.internal_issuer + url[len(self.issuer) :]
        return url

    # ---- JWKS ------------------------------------------------------------

    async def _fetch_jwks(self) -> dict:
        async with httpx.AsyncClient() as client:
            discovery = await client.get(
                f"{self.internal_issuer}/.well-known/openid-configuration",
                timeout=10,
            )
            discovery.raise_for_status()
            jwks_uri = self.rewrite_to_internal(discovery.json()["jwks_uri"])
            jwks = await client.get(jwks_uri, timeout=10)
            jwks.raise_for_status()
            return jwks.json()

    async def _get_jwks(self, *, force: bool = False) -> dict:
        now = time.time()
        if force or self._jwks is None or (now - self._jwks_fetched_at) > self._jwks_ttl:
            self._jwks = await self._fetch_jwks()
            self._jwks_fetched_at = now
        return self._jwks

    @staticmethod
    def _find_key(jwks: dict, kid: str | None) -> dict | None:
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None

    # ---- sub extraction --------------------------------------------------

    @staticmethod
    def _token_cache_key(token: str) -> str:
        # Hash the WHOLE token — signature alone collides on tampered-payload
        # + original-signature attacks and would silently bypass re-validation.
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    async def extract_sub(self, token: str) -> str:
        """Validate the JWT and return the ``sub`` claim.

        Results are cached by token hash for ``sub_cache_ttl`` seconds so a
        single request's re-entry points (ingress gate → list-filter →
        tool-call) each pay validation cost once.
        """
        cache_key = self._token_cache_key(token)
        now = time.time()
        cached = self._sub_cache.get(cache_key)
        if cached and (now - cached[1]) < self._sub_cache_ttl:
            return cached[0]

        try:
            header = _pyjwt.get_unverified_header(token)
        except Exception as exc:
            raise Exception(f"Invalid token header: {exc}") from exc

        kid = header.get("kid")
        jwks = await self._get_jwks()
        rsa_key = self._find_key(jwks, kid)
        if rsa_key is None:
            # Key rotation — refetch once, but rate-limit so a stream of
            # random-kid tokens can't turn into an IdP DoS.
            if (now - self._last_forced_refetch_at) >= self._FORCE_REFETCH_COOLDOWN:
                self._last_forced_refetch_at = now
                jwks = await self._get_jwks(force=True)
                rsa_key = self._find_key(jwks, kid)
        if rsa_key is None:
            raise Exception("Token signing key not found in JWKS")

        try:
            payload = _pyjwt.decode(
                token,
                RSAAlgorithm.from_jwk(rsa_key),
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False},
            )
        except _pyjwt.PyJWTError as exc:
            raise Exception(f"Token validation failed: {exc}") from exc

        sub = payload.get("sub")
        if not sub:
            raise Exception("Token missing 'sub' claim")

        self._sub_cache[cache_key] = (sub, now)
        return sub


def is_jwt(token: str) -> bool:
    """Three dot-separated segments → plausibly a JWT (not a LiteLLM
    virtual key like ``sk-...``)."""
    return bool(token) and token.count(".") == 2

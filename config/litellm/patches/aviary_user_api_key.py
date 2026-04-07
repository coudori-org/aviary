"""LiteLLM CustomLogger hook — per-user Anthropic API key injection via Vault.

For Anthropic backend requests, extracts the user's OIDC JWT from the
``X-Aviary-User-Token`` header, validates it against Keycloak JWKS, looks up
the user's personal Anthropic API key in Vault, and overrides the key used for
the upstream call.  Non-Anthropic backends (Ollama, vLLM, Bedrock) are
unaffected.

Loaded at Python startup via the ``.pth`` file alongside the streaming patch.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger("aviary.user_api_key")

# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

VAULT_ADDR = os.environ.get("VAULT_ADDR", "")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_INTERNAL_ISSUER = os.environ.get("OIDC_INTERNAL_ISSUER", "") or OIDC_ISSUER

# ---------------------------------------------------------------------------
# JWT library — prefer python-jose, fall back to PyJWT
# ---------------------------------------------------------------------------

try:
    from jose import jwt as _jose_jwt, JWTError  # type: ignore[import-untyped]

    def _decode_jwt(token: str, rsa_key: dict, issuer: str) -> dict:
        return _jose_jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )

    def _get_unverified_header(token: str) -> dict:
        return _jose_jwt.get_unverified_header(token)

except ImportError:
    import jwt as _pyjwt  # type: ignore[import-untyped]

    JWTError = _pyjwt.PyJWTError  # type: ignore[assignment,misc]

    def _decode_jwt(token: str, rsa_key: dict, issuer: str) -> dict:  # type: ignore[misc]
        from jwt.algorithms import RSAAlgorithm  # type: ignore[import-untyped]

        public_key = RSAAlgorithm.from_jwk(rsa_key)
        return _pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )

    def _get_unverified_header(token: str) -> dict:  # type: ignore[misc]
        return _pyjwt.get_unverified_header(token)

# ---------------------------------------------------------------------------
# JWKS cache (1-hour TTL)
# ---------------------------------------------------------------------------

_jwks: dict | None = None
_jwks_fetched_at: float = 0
_JWKS_TTL = 3600


def _internal_issuer() -> str:
    return OIDC_INTERNAL_ISSUER


async def _fetch_jwks() -> dict:
    discovery_url = f"{_internal_issuer()}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]
        # Rewrite public URL to internal URL for container-to-container access
        if OIDC_INTERNAL_ISSUER != OIDC_ISSUER and jwks_uri.startswith(OIDC_ISSUER):
            jwks_uri = OIDC_INTERNAL_ISSUER + jwks_uri[len(OIDC_ISSUER) :]
        resp2 = await client.get(jwks_uri, timeout=10)
        resp2.raise_for_status()
        return resp2.json()


async def _get_jwks(force: bool = False) -> dict:
    global _jwks, _jwks_fetched_at
    now = time.time()
    if force or _jwks is None or (now - _jwks_fetched_at) > _JWKS_TTL:
        _jwks = await _fetch_jwks()
        _jwks_fetched_at = now
    return _jwks


# ---------------------------------------------------------------------------
# JWT → sub cache (30-min TTL, keyed by token signature hash)
# ---------------------------------------------------------------------------

_sub_cache: dict[str, tuple[str, float]] = {}
_SUB_CACHE_TTL = 1800


def _token_cache_key(token: str) -> str:
    """Hash the JWT signature (last segment) for cache lookup."""
    parts = token.rsplit(".", 1)
    sig = parts[-1] if len(parts) > 1 else token
    return hashlib.sha256(sig.encode()).hexdigest()[:32]


async def _extract_sub(token: str) -> str:
    """Validate JWT and return the ``sub`` claim.  Results are cached."""
    cache_key = _token_cache_key(token)
    now = time.time()

    cached = _sub_cache.get(cache_key)
    if cached and (now - cached[1]) < _SUB_CACHE_TTL:
        return cached[0]

    try:
        header = _get_unverified_header(token)
    except Exception as exc:
        raise Exception(f"Invalid user token header: {exc}") from exc

    kid = header.get("kid")
    jwks = await _get_jwks()

    rsa_key = _find_key(jwks, kid)
    if rsa_key is None:
        # Key rotation — refetch JWKS once
        jwks = await _get_jwks(force=True)
        rsa_key = _find_key(jwks, kid)
    if rsa_key is None:
        raise Exception("Token signing key not found in JWKS — authentication failed")

    try:
        payload = _decode_jwt(token, rsa_key, OIDC_ISSUER)
    except JWTError as exc:
        raise Exception(f"Token validation failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise Exception("Token missing 'sub' claim — authentication failed")

    _sub_cache[cache_key] = (sub, now)
    return sub


def _find_key(jwks: dict, kid: str | None) -> dict | None:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


# ---------------------------------------------------------------------------
# Vault API key cache (30-sec TTL, keyed by sub)
# ---------------------------------------------------------------------------

_api_key_cache: dict[str, tuple[str | None, float]] = {}
_API_KEY_TTL = 30

VAULT_CREDENTIAL_NAME = "anthropic-api-key"


async def _get_vault_api_key(sub: str) -> str | None:
    """Fetch user's Anthropic API key from Vault.  Results are cached."""
    now = time.time()
    cached = _api_key_cache.get(sub)
    if cached and (now - cached[1]) < _API_KEY_TTL:
        return cached[0]

    if not VAULT_ADDR or not VAULT_TOKEN:
        raise Exception("Credential service not configured (Vault)")

    vault_path = f"aviary/credentials/{sub}/{VAULT_CREDENTIAL_NAME}"
    url = f"{VAULT_ADDR}/v1/secret/data/{vault_path}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"X-Vault-Token": VAULT_TOKEN},
                timeout=10,
            )
            if resp.status_code == 404:
                _api_key_cache[sub] = (None, now)
                return None
            resp.raise_for_status()
            token = resp.json()["data"]["data"].get("value")
            _api_key_cache[sub] = (token, now)
            return token
    except httpx.HTTPError as exc:
        raise Exception(f"Credential service unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# LiteLLM CustomLogger callback
# ---------------------------------------------------------------------------

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[import-untyped]
except ImportError:
    # At import time LiteLLM may not be fully loaded yet.
    # Defer — the .pth loader runs very early.
    CustomLogger = None  # type: ignore[assignment,misc]


def _register():
    """Register the hook with LiteLLM's callback system."""
    if CustomLogger is None:
        logger.warning("LiteLLM CustomLogger not available — skipping user API key hook")
        return

    import litellm  # type: ignore[import-untyped]
    from litellm.exceptions import AuthenticationError  # type: ignore[import-untyped]

    def _auth_error(msg: str) -> AuthenticationError:
        """Return a 401 AuthenticationError so the SDK does not retry."""
        return AuthenticationError(
            message=msg,
            llm_provider="anthropic",
            model="",
        )

    class AviaryUserApiKeyHook(CustomLogger):
        async def async_pre_call_hook(
            self,
            user_api_key_dict: dict[str, Any],
            cache: Any,
            data: dict[str, Any],
            call_type: str,
        ) -> dict[str, Any]:
            # Only intercept direct Anthropic backend requests.
            # Bedrock models routed through Portkey use anthropic/ prefix
            # but authenticate via AWS credentials, not Anthropic API keys.
            model = data.get("model", "")
            if not model.startswith("anthropic/"):
                return data

            # Skip Bedrock models — they use AWS credentials via Portkey
            extra_headers = data.get("extra_headers") or {}
            if extra_headers.get("x-portkey-provider") == "aws-bedrock":
                return data

            # Extract user JWT from request headers.
            # LiteLLM puts proxy_server_request at data top-level (Anthropic endpoint)
            # or inside metadata (OpenAI endpoint). Check both.
            proxy_req = data.get("proxy_server_request") or (
                data.get("metadata", {}).get("proxy_server_request")
            ) or {}
            headers = proxy_req.get("headers", {})
            user_token = headers.get("x-aviary-user-token")

            if not user_token:
                # No user token — internal call (e.g. API model listing) or
                # runtime not yet updated. Use config-level api_key as-is.
                return data

            # Validate JWT and extract sub
            try:
                sub = await _extract_sub(user_token)
            except Exception as exc:
                raise _auth_error(str(exc)) from exc

            # Look up user's API key in Vault
            try:
                api_key = await _get_vault_api_key(sub)
            except Exception as exc:
                raise _auth_error(f"Credential service error: {exc}") from exc

            if not api_key:
                raise _auth_error(
                    "No Anthropic API key configured for user. "
                    "Please add 'anthropic-api-key' credential in your profile settings."
                )

            # Override the API key for this request
            data["api_key"] = api_key
            if "litellm_params" in data:
                data["litellm_params"]["api_key"] = api_key

            logger.info("Using per-user Anthropic API key for sub=%s", sub)
            return data

    hook = AviaryUserApiKeyHook()
    litellm.callbacks.append(hook)
    logger.info("Aviary per-user API key hook registered")


# Auto-register on import — but only if OIDC is configured
if OIDC_ISSUER:
    try:
        _register()
    except Exception:
        logger.warning("Failed to register user API key hook", exc_info=True)
else:
    logger.info("OIDC_ISSUER not set — per-user API key hook disabled")

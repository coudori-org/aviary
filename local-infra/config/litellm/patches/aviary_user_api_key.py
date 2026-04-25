"""LiteLLM CustomLogger hook — per-user Anthropic API key injection via Vault.

On every Anthropic-backend request, extract the user's OIDC JWT from the
``X-Aviary-User-Token`` header, validate it against Keycloak, look up the
user's Anthropic API key in Vault, and override the upstream key.
Non-Anthropic backends (Bedrock, Ollama, vLLM) fall through untouched.

Loaded at Python startup via the ``.pth`` file alongside the MCP patch.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from aviary_jwt_util import JwtValidator
from aviary_vault_util import fetch_credential

logger = logging.getLogger("aviary.user_api_key")

OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
VAULT_CREDENTIAL_NAME = "anthropic-api-key"

_jwt = JwtValidator()


try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[import-untyped]
except ImportError:
    CustomLogger = None  # type: ignore[assignment,misc]


def _register() -> None:
    if CustomLogger is None:
        logger.warning("LiteLLM CustomLogger not available — skipping user API key hook")
        return

    import litellm  # type: ignore[import-untyped]
    from litellm.exceptions import AuthenticationError  # type: ignore[import-untyped]

    def _auth_error(msg: str) -> AuthenticationError:
        return AuthenticationError(message=msg, llm_provider="anthropic", model="")

    class AviaryUserApiKeyHook(CustomLogger):
        async def async_pre_call_hook(
            self,
            user_api_key_dict: dict[str, Any],
            cache: Any,
            data: dict[str, Any],
            call_type: str,
        ) -> dict[str, Any]:
            if not data.get("model", "").startswith("anthropic/"):
                return data

            # LiteLLM puts `proxy_server_request` at top-level for the Anthropic
            # endpoint but nests it under `metadata` for OpenAI — check both.
            proxy_req = data.get("proxy_server_request") or (
                data.get("metadata", {}).get("proxy_server_request")
            ) or {}
            user_token = (proxy_req.get("headers") or {}).get("x-aviary-user-token")
            if not user_token:
                # No user token = internal LiteLLM call (e.g. model listing) — leave key.
                return data

            try:
                sub = await _jwt.extract_sub(user_token)
            except Exception as exc:
                raise _auth_error(str(exc)) from exc

            try:
                api_key = await fetch_credential(sub, VAULT_CREDENTIAL_NAME)
            except Exception as exc:
                raise _auth_error(f"Credential service error: {exc}") from exc

            if not api_key:
                raise _auth_error(
                    "No Anthropic API key configured for user. "
                    "Add 'anthropic-api-key' in profile settings."
                )

            data["api_key"] = api_key
            if "litellm_params" in data:
                data["litellm_params"]["api_key"] = api_key
            logger.info("Using per-user Anthropic API key for sub=%s", sub)
            return data

    litellm.callbacks.append(AviaryUserApiKeyHook())
    logger.info("Aviary per-user API key hook registered")


if OIDC_ISSUER:
    try:
        _register()
    except Exception:
        logger.warning("Failed to register user API key hook", exc_info=True)
else:
    logger.info("OIDC_ISSUER not set — per-user API key hook disabled")

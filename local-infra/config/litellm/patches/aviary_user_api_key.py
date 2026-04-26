"""LiteLLM hook — inject the caller's Anthropic API key from Vault.

The Vault namespace is the ``X-Aviary-User-Sub`` header forwarded by the
caller. In production the upstream LLM-gateway team validates whatever
identity proof they require (typically a JWT they already trust) and
forwards the resolved sub. Locally there is no validation — we trust
the header. Non-Anthropic backends pass through untouched."""

from __future__ import annotations

import logging
from typing import Any

from aviary_vault_util import PLATFORM_NAMESPACE, fetch_credential

logger = logging.getLogger("aviary.user_api_key")

VAULT_CREDENTIAL_NAME = "anthropic-api-key"
SUB_HEADER = "x-aviary-user-sub"


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
            sub = (proxy_req.get("headers") or {}).get(SUB_HEADER)

            if not sub:
                # internal LiteLLM call (model listing etc.) — leave key alone
                return data

            try:
                api_key = await fetch_credential(
                    sub, PLATFORM_NAMESPACE, VAULT_CREDENTIAL_NAME,
                )
            except Exception as exc:
                raise _auth_error(f"Credential service error: {exc}") from exc

            if not api_key:
                raise _auth_error(
                    f"No Anthropic API key configured for sub={sub}. "
                    "Add 'anthropic-api-key' in profile settings."
                )

            data["api_key"] = api_key
            if "litellm_params" in data:
                data["litellm_params"]["api_key"] = api_key
            logger.info("Using per-user Anthropic API key for sub=%s", sub)
            return data

    litellm.callbacks.append(AviaryUserApiKeyHook())
    logger.info("Aviary per-user API key hook registered")


try:
    _register()
except Exception:
    logger.warning("Failed to register user API key hook", exc_info=True)

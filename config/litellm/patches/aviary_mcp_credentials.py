"""Per-user Vault credential injection + schema stripping for MCP tool calls
served through LiteLLM's aggregated ``/mcp`` endpoint.

For every ``call_mcp_tool`` request, extracts the user's OIDC JWT from the
``Authorization: Bearer ...`` header (surfaced as
``data["incoming_bearer_token"]`` by LiteLLM's MCP pre-call pipeline),
validates it against Keycloak JWKS, and injects per-user secrets fetched from
Vault at ``secret/aviary/credentials/{sub}/{vault_key}`` into the outbound
tool arguments.

Injected args are set on ``data["modified_arguments"]`` and LiteLLM merges
them into the outbound MCP ``tools/call`` before the backend MCP server sees
the request. Tool schemas exposed to the user's model have the injected
parameters stripped at discovery time (via a monkey-patch on
``MCPServerManager._get_tools_from_server``), so the model never fills them
in itself.

Loaded at Python startup via the ``.pth`` file alongside
``aviary_user_api_key`` (which provides the analogous Vault lookup for
Anthropic API keys on the inference path).
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx
import yaml

logger = logging.getLogger("aviary.mcp_credentials")

# ---------------------------------------------------------------------------
# Configuration (from environment)
# ---------------------------------------------------------------------------

VAULT_ADDR = os.environ.get("VAULT_ADDR", "")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
OIDC_INTERNAL_ISSUER = os.environ.get("OIDC_INTERNAL_ISSUER", "") or OIDC_ISSUER

INJECTION_CONFIG_PATH = os.environ.get(
    "AVIARY_MCP_INJECTION_CONFIG",
    "/app/aviary-mcp-secret-injection.yaml",
)

# MCP tool names arrive prefixed with the server alias. LiteLLM's default
# separator is ``-`` but Aviary has always used ``__`` (see the existing
# gateway's ``TOOL_NAME_SEPARATOR``). Keep the two in sync via
# ``MCP_TOOL_PREFIX_SEPARATOR`` on the LiteLLM container.
TOOL_NAME_SEPARATOR = os.environ.get("MCP_TOOL_PREFIX_SEPARATOR", "__")

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


async def _fetch_jwks() -> dict:
    discovery_url = f"{OIDC_INTERNAL_ISSUER}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(discovery_url, timeout=10)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]
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
    parts = token.rsplit(".", 1)
    sig = parts[-1] if len(parts) > 1 else token
    return hashlib.sha256(sig.encode()).hexdigest()[:32]


def _find_key(jwks: dict, kid: str | None) -> dict | None:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def _extract_sub(token: str) -> str:
    cache_key = _token_cache_key(token)
    now = time.time()

    cached = _sub_cache.get(cache_key)
    if cached and (now - cached[1]) < _SUB_CACHE_TTL:
        return cached[0]

    try:
        header = _get_unverified_header(token)
    except Exception as exc:
        raise Exception(f"Invalid MCP user token header: {exc}") from exc

    kid = header.get("kid")
    jwks = await _get_jwks()
    rsa_key = _find_key(jwks, kid)
    if rsa_key is None:
        jwks = await _get_jwks(force=True)
        rsa_key = _find_key(jwks, kid)
    if rsa_key is None:
        raise Exception("MCP token signing key not found in JWKS")

    try:
        payload = _decode_jwt(token, rsa_key, OIDC_ISSUER)
    except JWTError as exc:
        raise Exception(f"MCP token validation failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise Exception("MCP token missing 'sub' claim")

    _sub_cache[cache_key] = (sub, now)
    return sub


# ---------------------------------------------------------------------------
# Vault credential cache (30-sec TTL, keyed by (sub, vault_key))
# ---------------------------------------------------------------------------

_vault_cache: dict[tuple[str, str], tuple[str | None, float]] = {}
_VAULT_CACHE_TTL = 30


async def _get_vault_credential(sub: str, vault_key: str) -> str | None:
    now = time.time()
    ck = (sub, vault_key)
    cached = _vault_cache.get(ck)
    if cached and (now - cached[1]) < _VAULT_CACHE_TTL:
        return cached[0]

    if not VAULT_ADDR or not VAULT_TOKEN:
        raise Exception("Vault not configured for MCP credential injection")

    url = f"{VAULT_ADDR}/v1/secret/data/aviary/credentials/{sub}/{vault_key}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"X-Vault-Token": VAULT_TOKEN},
                timeout=10,
            )
            if resp.status_code == 404:
                _vault_cache[ck] = (None, now)
                return None
            resp.raise_for_status()
            value = resp.json()["data"]["data"].get("value")
            _vault_cache[ck] = (value, now)
            return value
    except httpx.HTTPError as exc:
        raise Exception(f"Vault error fetching '{vault_key}' for MCP: {exc}") from exc


# ---------------------------------------------------------------------------
# Injection config loader
# ---------------------------------------------------------------------------

_INJECTION_CFG: dict[str, dict] = {}


def _load_injection_config() -> None:
    global _INJECTION_CFG
    try:
        with open(INJECTION_CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
        _INJECTION_CFG = raw.get("servers", {}) or {}
        logger.info(
            "Loaded MCP secret injection config: %d servers from %s",
            len(_INJECTION_CFG),
            INJECTION_CONFIG_PATH,
        )
    except FileNotFoundError:
        logger.warning(
            "MCP secret injection config not found at %s — no args will be injected",
            INJECTION_CONFIG_PATH,
        )
        _INJECTION_CFG = {}


def _injected_args_for(server_name: str, tool_name: str) -> dict[str, dict]:
    """Return {arg_name: {vault_key: ...}} merging server-level + per-tool overrides."""
    server_cfg = _INJECTION_CFG.get(server_name) or {}
    if not server_cfg:
        return {}
    result = dict(server_cfg.get("args") or {})
    tool_cfg = (server_cfg.get("tools") or {}).get(tool_name) or {}
    if tool_cfg:
        result.update(tool_cfg.get("args") or {})
    return result


# ---------------------------------------------------------------------------
# server_name forwarding patch
# ---------------------------------------------------------------------------
#
# LiteLLM's ``_convert_mcp_to_llm_format`` surfaces ``mcp_tool_name`` and
# ``mcp_arguments`` to custom hooks but drops ``server_name`` on the floor.
# We need it to look up the right (server, arg) → vault_key mapping, so we
# monkey-patch the conversion to carry it through.

def _install_server_name_forwarder() -> None:
    try:
        from litellm.proxy.utils import ProxyLogging  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("LiteLLM ProxyLogging not importable — server_name forwarder disabled")
        return

    original = getattr(ProxyLogging, "_convert_mcp_to_llm_format", None)
    if original is None:
        logger.warning("ProxyLogging._convert_mcp_to_llm_format missing — skip forwarder")
        return
    if getattr(original, "_aviary_patched", False):
        return

    def patched(self, request_obj, kwargs):  # type: ignore[no-untyped-def]
        data = original(self, request_obj, kwargs)
        if isinstance(data, dict):
            data.setdefault("mcp_server_name", getattr(request_obj, "server_name", None))
        return data

    patched._aviary_patched = True  # type: ignore[attr-defined]
    ProxyLogging._convert_mcp_to_llm_format = patched  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Strip injected args from the tool schema on tools/list
# ---------------------------------------------------------------------------
#
# The previous standalone MCP Gateway hid Vault-injected parameters from the
# model so it never saw (or tried to fill) fields like ``jira_token``. LiteLLM
# proxies the backend's ``inputSchema`` untouched, so we wrap the manager's
# fetch-tools helper and strip the same fields before the model ever sees
# them. Tool-level overrides behave the same as the server-level defaults:
# each injected arg key is removed from ``properties`` and ``required``.

def _strip_injected_from_schema(schema: dict, injected: dict[str, dict]) -> dict:
    if not injected or not isinstance(schema, dict):
        return schema
    props = dict(schema.get("properties") or {})
    required = list(schema.get("required") or [])
    touched = False
    for name in injected:
        if name in props:
            props.pop(name, None)
            touched = True
        if name in required:
            required = [r for r in required if r != name]
            touched = True
    if not touched:
        return schema
    new_schema = dict(schema)
    new_schema["properties"] = props
    if required:
        new_schema["required"] = required
    else:
        new_schema.pop("required", None)
    return new_schema


def _unprefix_tool_name(prefixed: str, server_name: str) -> str:
    """LiteLLM's prefixed tool name → backend's original name."""
    prefix = f"{server_name}{TOOL_NAME_SEPARATOR}"
    return prefixed[len(prefix):] if prefixed.startswith(prefix) else prefixed


def _install_tools_list_stripper() -> None:
    try:
        from litellm.proxy._experimental.mcp_server import mcp_server_manager  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("LiteLLM MCPServerManager not importable — tools/list stripper disabled")
        return

    cls = getattr(mcp_server_manager, "MCPServerManager", None)
    if cls is None:
        logger.warning("MCPServerManager class missing — skip tools/list stripper")
        return

    original = getattr(cls, "_get_tools_from_server", None)
    if original is None or getattr(original, "_aviary_patched", False):
        return

    async def patched(self, server, *args, **kwargs):  # type: ignore[no-untyped-def]
        tools = await original(self, server, *args, **kwargs)
        server_name = getattr(server, "name", None) or getattr(server, "alias", None)
        if not server_name or not tools:
            return tools
        for tool in tools:
            raw_name = _unprefix_tool_name(tool.name, server_name)
            injection = _injected_args_for(server_name, raw_name)
            if not injection:
                continue
            tool.inputSchema = _strip_injected_from_schema(tool.inputSchema or {}, injection)
        return tools

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls._get_tools_from_server = patched  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# LiteLLM CustomLogger callback
# ---------------------------------------------------------------------------

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[import-untyped]
except ImportError:
    CustomLogger = None  # type: ignore[assignment,misc]


def _split_qualified_name(qualified: str) -> tuple[str | None, str]:
    """``server__tool`` → ``(server, tool)``. Unprefixed → ``(None, name)``."""
    if TOOL_NAME_SEPARATOR in qualified:
        srv, tool = qualified.split(TOOL_NAME_SEPARATOR, 1)
        return srv, tool
    return None, qualified


def _register() -> None:
    if CustomLogger is None:
        logger.warning("LiteLLM CustomLogger not available — skipping MCP credentials hook")
        return

    import litellm  # type: ignore[import-untyped]
    from fastapi import HTTPException  # type: ignore[import-untyped]

    class AviaryMCPCredentialsHook(CustomLogger):
        async def async_pre_call_hook(
            self,
            user_api_key_dict: Any,
            cache: Any,
            data: dict[str, Any],
            call_type: str,
        ) -> dict[str, Any]:
            if call_type != "call_mcp_tool":
                return data

            user_token = data.get("incoming_bearer_token")
            if not user_token:
                raise HTTPException(
                    status_code=401,
                    detail={"error": "MCP call missing Bearer token"},
                )

            server_name = data.get("mcp_server_name")
            tool_name = data.get("mcp_tool_name") or ""
            # Fallback when the server_name forwarder isn't active yet
            # (stale image / monkey-patch lost across restarts) — derive
            # it from the prefixed tool name instead.
            if not server_name:
                server_name, tool_name = _split_qualified_name(tool_name)
            if not server_name:
                return data

            injection = _injected_args_for(server_name, tool_name)
            if not injection:
                return data

            try:
                sub = await _extract_sub(user_token)
            except Exception as exc:
                raise HTTPException(
                    status_code=401,
                    detail={"error": f"MCP auth failed: {exc}"},
                ) from exc

            arguments = dict(data.get("mcp_arguments") or {})
            missing: list[str] = []
            for arg_name, mapping in injection.items():
                vault_key = mapping.get("vault_key") if isinstance(mapping, dict) else None
                if not vault_key:
                    continue
                secret = await _get_vault_credential(sub, vault_key)
                if secret is None:
                    missing.append(vault_key)
                    continue
                arguments[arg_name] = secret

            if missing:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": (
                            f"Missing MCP credentials for user: {', '.join(missing)}. "
                            "Ask your admin to configure them in your profile."
                        )
                    },
                )

            data["modified_arguments"] = arguments
            logger.info(
                "MCP credential injection sub=%s server=%s tool=%s injected=%s",
                sub,
                server_name,
                tool_name,
                list(injection.keys()),
            )
            return data

    hook = AviaryMCPCredentialsHook()
    litellm.callbacks.append(hook)
    logger.info("Aviary MCP credential injection hook registered")


if OIDC_ISSUER:
    try:
        _load_injection_config()
        _install_server_name_forwarder()
        _install_tools_list_stripper()
        _register()
    except Exception:
        logger.warning("Failed to register MCP credential injection hook", exc_info=True)
else:
    logger.info("OIDC_ISSUER not set — MCP credential injection hook disabled")

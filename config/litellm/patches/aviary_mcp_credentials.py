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
    # Hash the entire token — signature alone is not a unique key because
    # a tampered payload + original signature collides with the valid
    # token's cache entry and silently bypasses re-validation.
    return hashlib.sha256(token.encode()).hexdigest()[:32]


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

def _install_mcp_request_auth_gate() -> None:
    """Close LiteLLM's OAuth2-passthrough fail-open on ``/mcp``.

    Upstream ``MCPRequestHandler.process_mcp_request`` silently accepts any
    Bearer token that isn't a valid LiteLLM virtual key by downgrading to
    an empty ``UserAPIKeyAuth()`` (see ``user_api_key_auth_mcp.py`` OAuth2
    passthrough branch). We wrap that method so a tampered / expired /
    non-Keycloak JWT raises 401 at request ingress, before any list or
    call handler runs. Master keys (``sk-*``) fall through untouched —
    LiteLLM's own key auth already vetted them.
    """
    try:
        from litellm.proxy._experimental.mcp_server.auth import (  # type: ignore[import-untyped]
            user_api_key_auth_mcp as mcp_auth_mod,
        )
    except ImportError:
        logger.warning("MCP auth module not importable — JWT ingress gate disabled")
        return

    cls = getattr(mcp_auth_mod, "MCPRequestHandler", None)
    if cls is None:
        return

    original = getattr(cls, "process_mcp_request", None)
    if original is None or getattr(original, "_aviary_patched", False):
        return

    from fastapi import HTTPException  # type: ignore[import-untyped]

    async def patched(scope):  # type: ignore[no-untyped-def]
        result = await original(scope)
        # Extract the bearer from the request headers we just saw.
        headers = dict(result[-1]) if result else {}
        token = _bearer_from_headers(headers)
        # Only enforce for actual JWTs — master keys are handled upstream.
        if token and not token.startswith("sk-") and _is_jwt(token):
            try:
                await _extract_sub(token)
            except Exception as exc:
                raise HTTPException(
                    status_code=401,
                    detail={"error": f"MCP JWT validation failed: {exc}"},
                ) from exc
        return result

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls.process_mcp_request = staticmethod(patched)  # type: ignore[method-assign]


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


ALLOWED_TOOLS_HEADER = "x-aviary-allowed-tools"


# ---------------------------------------------------------------------------
# Universal JWT gate for MCP traffic
# ---------------------------------------------------------------------------
#
# LiteLLM OSS doesn't run its built-in JWT auth on the MCP endpoint
# (see user_api_key_auth_mcp.py's OAuth2 passthrough which silently
# fail-opens on invalid credentials), so we validate here before any
# catalog data or tool invocation is allowed out.


def _normalized_headers(raw_headers: Any) -> dict[str, str]:
    if not isinstance(raw_headers, dict):
        return {}
    return {k.lower(): v for k, v in raw_headers.items()}


def _bearer_from_headers(raw_headers: Any) -> str | None:
    headers = _normalized_headers(raw_headers)
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return auth[len("bearer ") :].strip()


def _is_jwt(token: str) -> bool:
    """LiteLLM-style JWT shape check — three dot-separated segments."""
    return bool(token) and token.count(".") == 2


async def _require_valid_mcp_bearer(raw_headers: Any) -> str | None:
    """Require a valid Bearer credential on every MCP request.

    * Missing / malformed Authorization header → 401.
    * LiteLLM virtual keys (``sk-*``) pass through — LiteLLM's own key
      auth handles them at the upstream entry point.
    * Keycloak JWTs are validated against JWKS (same path as Vault
      credential injection). Any validation failure → 401.

    Returns the raw bearer string on success, or ``None`` when headers
    aren't a plain dict (e.g., internal in-process calls where no request
    context exists — those bypass MCP auth entirely).
    """
    from fastapi import HTTPException  # local import — guardrail runs late

    if not isinstance(raw_headers, dict):
        return None
    token = _bearer_from_headers(raw_headers)
    if not token:
        raise HTTPException(
            status_code=401, detail={"error": "MCP request missing Bearer credential"}
        )
    if token.startswith("sk-") or not _is_jwt(token):
        return token
    try:
        await _extract_sub(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail={"error": f"MCP JWT validation failed: {exc}"}
        ) from exc
    return token


async def _maybe_extract_sub(token: str | None) -> str | None:
    """Best-effort ``sub`` extraction for downstream hooks (RBAC stub, etc.).
    Skips master keys and returns ``None`` on any failure — caller should
    have already enforced validation via ``_require_valid_mcp_bearer``."""
    if not token or token.startswith("sk-") or not _is_jwt(token):
        return None
    try:
        return await _extract_sub(token)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# RBAC filter stub — future extension point
# ---------------------------------------------------------------------------


async def _rbac_filter_tools(
    server: Any, tools: list, raw_headers: Any, user_sub: str | None,
) -> list:
    """Per-user/server/tool RBAC decision.

    **Today:** no-op. The only visibility gate is LiteLLM's
    ``allow_all_keys`` flag on each registered server (applied upstream
    in ``MCPServerManager.get_all_allowed_mcp_servers``). That already
    covers the binary public/private model.

    **Future:** when fine-grained RBAC lands ("user U in team T may see
    server S"), this is where it plugs in — either by consulting an
    Aviary-owned policy source (team membership, realm roles in the JWT,
    an RBAC DB) or by calling back into LiteLLM with a per-user virtual
    key. The signature intentionally carries enough context
    (``server``, ``tools``, ``raw_headers``, ``user_sub``) so either
    server-level or tool-level policies can be expressed without changing
    the call-site in ``_install_tools_list_stripper``.
    """
    return tools


def _allowed_tools_from_headers(raw_headers: Any) -> set[str] | None:
    """Extract the caller's agent-scoped tool allow-list from request headers.

    ``None`` means "no allow-list was provided — full catalog visible"
    (backward-compat for non-Aviary callers). Empty set means "no tools
    visible".
    """
    if not isinstance(raw_headers, dict):
        return None
    lower = {k.lower(): v for k, v in raw_headers.items()}
    raw = lower.get(ALLOWED_TOOLS_HEADER)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = ",".join(raw)
    return {t.strip() for t in str(raw).split(",") if t.strip()}


def _install_tools_list_stripper() -> None:
    """Schema strip (Vault-injected args) + caller-scoped visibility filter
    on ``MCPServerManager._get_tools_from_server``.

    The visibility filter reads ``X-Aviary-Allowed-Tools`` from the caller's
    request headers (the runtime attaches this on every MCP connection,
    computed from the agent's ``mcp_agent_tool_bindings``). Only tools whose
    prefixed name (``{server}__{tool}``) appears in the header survive; the
    rest are dropped before the MCP SDK ever advertises them to the model.
    """
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
        raw_headers = kwargs.get("raw_headers")
        # Enforce auth before any catalog bytes leave LiteLLM. Internal
        # in-process calls (no raw_headers) skip — they originate from
        # trusted admin code paths.
        token = await _require_valid_mcp_bearer(raw_headers)

        tools = await original(self, server, *args, **kwargs)
        server_name = getattr(server, "name", None) or getattr(server, "alias", None)
        if not server_name or not tools:
            return tools

        sub = await _maybe_extract_sub(token)
        tools = await _rbac_filter_tools(server, tools, raw_headers, sub)

        for tool in tools:
            raw_name = _unprefix_tool_name(tool.name, server_name)
            injection = _injected_args_for(server_name, raw_name)
            if injection:
                tool.inputSchema = _strip_injected_from_schema(
                    tool.inputSchema or {}, injection
                )

        allowed = _allowed_tools_from_headers(raw_headers)
        if allowed is not None:
            tools = [t for t in tools if t.name in allowed]
            logger.debug(
                "tools/list filter server=%s kept=%d (allowed=%d)",
                server_name, len(tools), len(allowed),
            )
        return tools

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls._get_tools_from_server = patched  # type: ignore[method-assign]


def _install_tools_call_gate() -> None:
    """Reject ``tools/call`` requests for tools outside the caller's
    ``X-Aviary-Allowed-Tools`` header — defense in depth against agents that
    try to invoke tools they don't have bound."""
    try:
        from litellm.proxy._experimental.mcp_server import mcp_server_manager  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("MCPServerManager not importable — tools/call gate disabled")
        return

    cls = getattr(mcp_server_manager, "MCPServerManager", None)
    if cls is None:
        return

    original = getattr(cls, "call_tool", None)
    if original is None or getattr(original, "_aviary_patched", False):
        return

    async def patched(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        # ``call_tool`` is keyword-heavy; handle both positional + kw callers.
        name = kwargs.get("name")
        server_name = kwargs.get("server_name")
        if name is None and len(args) >= 2:
            server_name = args[0] if server_name is None else server_name
            name = args[1]
        raw_headers = kwargs.get("raw_headers")

        # Enforce JWT before anything else — matches the tools/list path.
        await _require_valid_mcp_bearer(raw_headers)

        allowed = _allowed_tools_from_headers(raw_headers)
        if allowed is not None and name and server_name:
            prefixed = f"{server_name}{TOOL_NAME_SEPARATOR}{name}"
            if prefixed not in allowed and name not in allowed:
                from mcp.types import CallToolResult, TextContent  # type: ignore[import-untyped]
                logger.info(
                    "tools/call denied server=%s tool=%s (not in allowed set)",
                    server_name, name,
                )
                return CallToolResult(
                    content=[TextContent(
                        type="text",
                        text=(
                            f"Tool '{prefixed}' is not bound to this agent. "
                            "Update the agent's tool selection in the UI."
                        ),
                    )],
                    isError=True,
                )
        return await original(self, *args, **kwargs)

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls.call_tool = patched  # type: ignore[method-assign]


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


def _install_auth_noise_filter() -> None:
    """Silence LiteLLM's virtual-key assertion for JWT bearers.

    `/mcp` ingress auth accepts JWTs via the OAuth2-passthrough branch, but
    LiteLLM's outer `user_api_key_auth` still asserts `sk-*` first and logs
    the resulting AssertionError before the fallback runs. Our JWT gate
    (`_install_mcp_request_auth_gate`) is the real validator, so this
    outer noise is spurious — drop the record.
    """
    import logging as _logging

    class _VirtualKeyAssertFilter(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            msg = record.getMessage()
            return "LiteLLM Virtual Key expected" not in msg

    _logging.getLogger("LiteLLM Proxy").addFilter(_VirtualKeyAssertFilter())


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

            # Validate JWT on every tool call, regardless of whether the
            # target server needs Vault injection. Master keys (`sk-*`) are
            # passed through unchanged — LiteLLM's own key ACL vets them.
            if not user_token.startswith("sk-") and _is_jwt(user_token):
                try:
                    sub = await _extract_sub(user_token)
                except Exception as exc:
                    raise HTTPException(
                        status_code=401,
                        detail={"error": f"MCP JWT validation failed: {exc}"},
                    ) from exc
            else:
                sub = None

            server_name = data.get("mcp_server_name")
            tool_name = data.get("mcp_tool_name") or ""
            if not server_name:
                server_name, tool_name = _split_qualified_name(tool_name)
            if not server_name:
                return data

            injection = _injected_args_for(server_name, tool_name)
            if not injection:
                return data

            if sub is None:
                raise HTTPException(
                    status_code=401,
                    detail={"error": "MCP credential injection requires a user JWT"},
                )

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
        _install_mcp_request_auth_gate()
        _install_server_name_forwarder()
        _install_tools_list_stripper()
        _install_tools_call_gate()
        _install_auth_noise_filter()
        _register()
    except Exception:
        logger.warning("Failed to register MCP credential injection hook", exc_info=True)
else:
    logger.info("OIDC_ISSUER not set — MCP credential injection hook disabled")

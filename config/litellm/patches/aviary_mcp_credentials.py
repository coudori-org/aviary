"""Per-user Vault credential injection + schema stripping + JWT gate for
MCP tool calls served through LiteLLM's aggregated ``/mcp`` endpoint.

Pipeline:
  * request ingress → validate Bearer (LiteLLM OSS fail-opens here — we don't)
  * tools/list → strip Vault-injected args from inputSchema + filter by
                 caller-scoped X-Aviary-Allowed-Tools header
  * tools/call → re-validate + allow-list gate + inject Vault secrets
                 into ``modified_arguments``
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

from aviary_jwt_util import JwtValidator, is_jwt
from aviary_vault_util import fetch_credential

logger = logging.getLogger("aviary.mcp_credentials")

OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
TOOL_NAME_SEPARATOR = os.environ.get("MCP_TOOL_PREFIX_SEPARATOR", "__")
INJECTION_CONFIG_PATH = os.environ.get(
    "AVIARY_MCP_INJECTION_CONFIG", "/app/aviary-mcp-secret-injection.yaml",
)
ALLOWED_TOOLS_HEADER = "x-aviary-allowed-tools"

_jwt = JwtValidator()


# ── Injection config ───────────────────────────────────────────────────────

_INJECTION_CFG: dict[str, dict] = {}


def _load_injection_config() -> None:
    global _INJECTION_CFG
    try:
        with open(INJECTION_CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
        _INJECTION_CFG = raw.get("servers", {}) or {}
        logger.info(
            "Loaded MCP secret injection config: %d servers from %s",
            len(_INJECTION_CFG), INJECTION_CONFIG_PATH,
        )
    except FileNotFoundError:
        logger.warning(
            "MCP secret injection config not found at %s — no args will be injected",
            INJECTION_CONFIG_PATH,
        )
        _INJECTION_CFG = {}


def _injected_args_for(server_name: str, tool_name: str) -> dict[str, dict]:
    """{arg_name: {vault_key: ...}} — server defaults + per-tool overrides."""
    server_cfg = _INJECTION_CFG.get(server_name) or {}
    if not server_cfg:
        return {}
    result = dict(server_cfg.get("args") or {})
    tool_cfg = (server_cfg.get("tools") or {}).get(tool_name) or {}
    if tool_cfg:
        result.update(tool_cfg.get("args") or {})
    return result


# ── Header helpers ─────────────────────────────────────────────────────────

def _bearer_from_headers(raw_headers: Any) -> str | None:
    if not isinstance(raw_headers, dict):
        return None
    lower = {k.lower(): v for k, v in raw_headers.items()}
    auth = lower.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    return auth[len("bearer ") :].strip()


def _allowed_tools_from_headers(raw_headers: Any) -> set[str] | None:
    """Caller's agent-scoped allow-list. ``None`` = no header sent, full
    catalog visible (non-Aviary callers)."""
    if not isinstance(raw_headers, dict):
        return None
    lower = {k.lower(): v for k, v in raw_headers.items()}
    raw = lower.get(ALLOWED_TOOLS_HEADER)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        raw = ",".join(raw)
    return {t.strip() for t in str(raw).split(",") if t.strip()}


async def _require_valid_mcp_bearer(raw_headers: Any) -> str | None:
    """Validate the Bearer on every MCP request. Master keys (sk-*) pass
    through unchanged — LiteLLM's own key auth already vetted them.
    Returns the raw token on success, ``None`` when ``raw_headers`` isn't
    a dict (internal in-process calls with no request context)."""
    from fastapi import HTTPException  # type: ignore[import-untyped]

    if not isinstance(raw_headers, dict):
        return None
    token = _bearer_from_headers(raw_headers)
    if not token:
        raise HTTPException(
            status_code=401, detail={"error": "MCP request missing Bearer credential"}
        )
    if token.startswith("sk-") or not is_jwt(token):
        return token
    try:
        await _jwt.extract_sub(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401, detail={"error": f"MCP JWT validation failed: {exc}"}
        ) from exc
    return token


async def _maybe_extract_sub(token: str | None) -> str | None:
    """Best-effort sub for downstream hooks. Skips master keys and swallows
    failures — caller should have already enforced validation."""
    if not token or token.startswith("sk-") or not is_jwt(token):
        return None
    try:
        return await _jwt.extract_sub(token)
    except Exception:
        return None


# ── LiteLLM monkey-patches ─────────────────────────────────────────────────

def _install_mcp_request_auth_gate() -> None:
    """Close LiteLLM OSS's OAuth2-passthrough fail-open on ``/mcp``.

    Upstream silently accepts any Bearer that isn't a virtual key by
    downgrading to an empty ``UserAPIKeyAuth()``. We wrap
    ``MCPRequestHandler.process_mcp_request`` so invalid/tampered/expired
    JWTs 401 at ingress before any list or call handler runs. Master keys
    (sk-*) fall through — already vetted by LiteLLM.
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
        headers = dict(result[-1]) if result else {}
        token = _bearer_from_headers(headers)
        if token and not token.startswith("sk-") and is_jwt(token):
            try:
                await _jwt.extract_sub(token)
            except Exception as exc:
                raise HTTPException(
                    status_code=401,
                    detail={"error": f"MCP JWT validation failed: {exc}"},
                ) from exc
        return result

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls.process_mcp_request = staticmethod(patched)  # type: ignore[method-assign]


def _install_server_name_forwarder() -> None:
    """Carry ``server_name`` through ``_convert_mcp_to_llm_format`` — LiteLLM
    drops it, but we need it to look up per-(server, arg) vault_key mappings."""
    try:
        from litellm.proxy.utils import ProxyLogging  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("LiteLLM ProxyLogging not importable — server_name forwarder disabled")
        return

    original = getattr(ProxyLogging, "_convert_mcp_to_llm_format", None)
    if original is None or getattr(original, "_aviary_patched", False):
        return

    def patched(self, request_obj, kwargs):  # type: ignore[no-untyped-def]
        data = original(self, request_obj, kwargs)
        if isinstance(data, dict):
            data.setdefault("mcp_server_name", getattr(request_obj, "server_name", None))
        return data

    patched._aviary_patched = True  # type: ignore[attr-defined]
    ProxyLogging._convert_mcp_to_llm_format = patched  # type: ignore[method-assign]


def _strip_injected_from_schema(schema: dict, injected: dict[str, dict]) -> dict:
    """Remove Vault-injected args from ``properties`` + ``required`` so the
    model never sees (or tries to fill) fields like ``jira_token``."""
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
    prefix = f"{server_name}{TOOL_NAME_SEPARATOR}"
    return prefixed[len(prefix):] if prefixed.startswith(prefix) else prefixed


async def _rbac_filter_tools(
    server: Any, tools: list, raw_headers: Any, user_sub: str | None,
) -> list:
    """RBAC hook — today a no-op. LiteLLM's ``allow_all_keys`` flag covers
    the binary public/private model. Fine-grained per-user grants plug in
    here when they land."""
    return tools


def _install_tools_list_stripper() -> None:
    """tools/list: JWT gate + RBAC + schema strip + allow-list filter."""
    try:
        from litellm.proxy._experimental.mcp_server import mcp_server_manager  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("LiteLLM MCPServerManager not importable — tools/list stripper disabled")
        return

    cls = getattr(mcp_server_manager, "MCPServerManager", None)
    original = getattr(cls, "_get_tools_from_server", None) if cls else None
    if original is None or getattr(original, "_aviary_patched", False):
        return

    async def patched(self, server, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_headers = kwargs.get("raw_headers")
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
                    tool.inputSchema or {}, injection,
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
    """tools/call: JWT gate + deny tools outside the caller's allow-list."""
    try:
        from litellm.proxy._experimental.mcp_server import mcp_server_manager  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("MCPServerManager not importable — tools/call gate disabled")
        return

    cls = getattr(mcp_server_manager, "MCPServerManager", None)
    original = getattr(cls, "call_tool", None) if cls else None
    if original is None or getattr(original, "_aviary_patched", False):
        return

    async def patched(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        name = kwargs.get("name")
        server_name = kwargs.get("server_name")
        if name is None and len(args) >= 2:
            server_name = args[0] if server_name is None else server_name
            name = args[1]
        raw_headers = kwargs.get("raw_headers")

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


def _install_auth_noise_filter() -> None:
    """Silence LiteLLM's virtual-key assertion log for JWT bearers.

    ``/mcp`` ingress accepts JWTs via the OAuth2-passthrough branch, but
    LiteLLM's outer ``user_api_key_auth`` still asserts sk-* first and
    logs the resulting AssertionError before the fallback runs. Our JWT
    gate is the real validator — drop the spurious record.
    """
    import logging as _logging

    class _VirtualKeyAssertFilter(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            return "LiteLLM Virtual Key expected" not in record.getMessage()

    _logging.getLogger("LiteLLM Proxy").addFilter(_VirtualKeyAssertFilter())


# ── tools/call hook: Vault injection ───────────────────────────────────────

try:
    from litellm.integrations.custom_logger import CustomLogger  # type: ignore[import-untyped]
except ImportError:
    CustomLogger = None  # type: ignore[assignment,misc]


def _split_qualified_name(qualified: str) -> tuple[str | None, str]:
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

            if not user_token.startswith("sk-") and is_jwt(user_token):
                try:
                    sub = await _jwt.extract_sub(user_token)
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
                secret = await fetch_credential(sub, vault_key)
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
                sub, server_name, tool_name, list(injection.keys()),
            )
            return data

    litellm.callbacks.append(AviaryMCPCredentialsHook())
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

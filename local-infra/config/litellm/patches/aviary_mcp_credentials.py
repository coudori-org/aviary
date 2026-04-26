"""Per-user Vault credential injection + schema stripping for MCP tools
served through LiteLLM's aggregated ``/mcp`` endpoint.

Pipeline:
  * tools/list → strip Vault-injected args from inputSchema + filter by
                 caller-scoped X-Aviary-Allowed-Tools header
  * tools/call → allow-list gate + inject Vault secrets into
                 ``modified_arguments`` (sub from X-Aviary-User-Sub header,
                 propagated to the inner pre_mcp_call hook via contextvar)
"""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

import yaml

from aviary_vault_util import fetch_credential

logger = logging.getLogger("aviary.mcp_credentials")

TOOL_NAME_SEPARATOR = os.environ.get("MCP_TOOL_PREFIX_SEPARATOR", "__")
INJECTION_CONFIG_PATH = os.environ.get(
    "AVIARY_MCP_INJECTION_CONFIG", "/app/aviary-mcp-secret-injection.yaml",
)
ALLOWED_TOOLS_HEADER = "x-aviary-allowed-tools"
SUB_HEADER = "x-aviary-user-sub"

# tools/call gate has raw_headers; the inner pre_mcp_call hook only sees
# ``data`` — bridge them with a contextvar set in the gate.
_user_sub_cv: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "aviary_user_sub", default=None,
)


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


def _sub_from_headers(raw_headers: Any) -> str | None:
    if not isinstance(raw_headers, dict):
        return None
    lower = {k.lower(): v for k, v in raw_headers.items()}
    return lower.get(SUB_HEADER) or None


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
    # Placeholder for per-user RBAC grants.
    return tools


def _install_tools_list_stripper() -> None:
    """tools/list: RBAC + schema strip + allow-list filter."""
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
        tools = await original(self, server, *args, **kwargs)
        server_name = getattr(server, "name", None) or getattr(server, "alias", None)
        if not server_name or not tools:
            return tools

        sub = _sub_from_headers(raw_headers)
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
    """tools/call: deny tools outside the caller's allow-list, and stash sub
    in a contextvar so the inner pre_mcp_call hook can resolve Vault keys."""
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

        token = _user_sub_cv.set(_sub_from_headers(raw_headers))
        try:
            return await original(self, *args, **kwargs)
        finally:
            _user_sub_cv.reset(token)

    patched._aviary_patched = True  # type: ignore[attr-defined]
    cls.call_tool = patched  # type: ignore[method-assign]


def _install_auth_noise_filter() -> None:
    """Silence LiteLLM's virtual-key assertion log.

    ``/mcp`` accepts non-sk-* bearers via the OAuth2-passthrough branch,
    but LiteLLM's outer ``user_api_key_auth`` still asserts sk-* first
    and logs the resulting AssertionError before the fallback runs.
    """
    import logging as _logging

    class _VirtualKeyAssertFilter(_logging.Filter):
        def filter(self, record: _logging.LogRecord) -> bool:
            return "LiteLLM Virtual Key expected" not in record.getMessage()

    _logging.getLogger("LiteLLM Proxy").addFilter(_VirtualKeyAssertFilter())


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

            server_name = data.get("mcp_server_name")
            tool_name = data.get("mcp_tool_name") or ""
            if not server_name:
                server_name, tool_name = _split_qualified_name(tool_name)
            if not server_name:
                return data

            injection = _injected_args_for(server_name, tool_name)
            if not injection:
                return data

            sub = _user_sub_cv.get()
            if not sub:
                raise HTTPException(
                    status_code=401,
                    detail={"error": "MCP credential injection requires X-Aviary-User-Sub header"},
                )

            arguments = dict(data.get("mcp_arguments") or {})
            missing: list[str] = []
            for arg_name, mapping in injection.items():
                vault_key = mapping.get("vault_key") if isinstance(mapping, dict) else None
                if not vault_key:
                    continue
                secret = await fetch_credential(sub, server_name, vault_key)
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


try:
    _load_injection_config()
    _install_server_name_forwarder()
    _install_tools_list_stripper()
    _install_tools_call_gate()
    _install_auth_noise_filter()
    _register()
    logger.info("Aviary MCP hooks installed")
except Exception:
    logger.warning("Failed to register MCP credential injection hook", exc_info=True)

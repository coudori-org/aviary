"""Loader for the MCP credential injection schema.

Same file LiteLLM reads (``mcp-secret-injection.yaml``); the API mounts it
read-only so the credentials screen can ask "for each server the user can
see, which vault keys does it need?" without round-tripping to LiteLLM.

Reloaded on every fetch — the file is small and operators edit it in place.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import settings


def _load() -> dict[str, dict]:
    p = Path(settings.mcp_injection_config_path)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    servers = raw.get("servers") or {}
    return servers if isinstance(servers, dict) else {}


def server_credential_keys() -> dict[str, list[str]]:
    """``{server_name: [vault_key, …]}`` — server defaults plus per-tool
    overrides, deduplicated. Order preserves first-seen.
    """
    out: dict[str, list[str]] = {}
    for server_name, cfg in _load().items():
        if not isinstance(cfg, dict):
            continue
        seen: list[str] = []
        for arg_cfg in (cfg.get("args") or {}).values():
            key = (arg_cfg or {}).get("vault_key") if isinstance(arg_cfg, dict) else None
            if key and key not in seen:
                seen.append(key)
        for tool_cfg in (cfg.get("tools") or {}).values():
            for arg_cfg in (tool_cfg or {}).get("args", {}).values():
                key = (arg_cfg or {}).get("vault_key") if isinstance(arg_cfg, dict) else None
                if key and key not in seen:
                    seen.append(key)
        if seen:
            out[server_name] = seen
    return out

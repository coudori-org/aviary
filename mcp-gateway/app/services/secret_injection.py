"""Secret injection config: which tool args are auto-filled from Vault.

Loaded once at module import from `mcp-gateway/config/secret-injection.yaml`.
Two consumers:

  - Gateway runtime (`mcp/gateway_server.py`)
      - Strips injected args from `tools/list` so Claude never sees them
      - Fetches them from Vault and merges into `tools/call` arguments

  - Platform server registration (`services/platform_servers.py`)
      - Annotates the discovered `inputSchema` with `x-injected-from-vault`
        so the catalog UI can show users which credentials a tool needs
"""

import copy
import logging
import os

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "secret-injection.yaml"
)

INJECTED_VAULT_KEY_PROP = "x-injected-from-vault"

_INJECTION_CONFIG: dict[str, dict] = {}
try:
    with open(_CONFIG_PATH) as f:
        _raw = yaml.safe_load(f)
    _INJECTION_CONFIG = _raw.get("servers", {}) if _raw else {}
    logger.info("Loaded secret injection config for %d servers", len(_INJECTION_CONFIG))
except FileNotFoundError:
    logger.warning("secret-injection.yaml not found at %s", _CONFIG_PATH)


def get_injected_args(server_name: str, tool_name: str) -> dict[str, dict]:
    """Return {arg_name: {vault_key: ...}} for a tool.

    Merges server-level args with per-tool overrides (tool wins).
    """
    server_cfg = _INJECTION_CONFIG.get(server_name, {})
    if not server_cfg:
        return {}
    result = dict(server_cfg.get("args", {}))
    tool_cfg = server_cfg.get("tools", {}).get(tool_name, {})
    if tool_cfg:
        result.update(tool_cfg.get("args", {}))
    return result


def strip_injected_from_schema(schema: dict, injected_args: dict[str, dict]) -> dict:
    """Remove injected argument names from a JSON Schema so Claude never sees them."""
    if not injected_args:
        return schema
    schema = copy.deepcopy(schema)
    props = schema.get("properties", {})
    required = schema.get("required", [])
    for arg_name in injected_args:
        props.pop(arg_name, None)
        if arg_name in required:
            required = [r for r in required if r != arg_name]
    if props:
        schema["properties"] = props
    if required:
        schema["required"] = required
    elif "required" in schema:
        del schema["required"]
    return schema


def annotate_schema_with_injections(
    schema: dict, injected_args: dict[str, dict]
) -> dict:
    """Tag injected properties with `x-injected-from-vault: <vault_key>`.

    Mutates the schema in place. The annotation is a JSON Schema extension
    that flows through the DB and API server unchanged so the catalog UI
    can show users which Vault credentials a tool depends on. Properties
    that aren't injected are left untouched.
    """
    if not injected_args:
        return schema
    props = schema.get("properties")
    if not isinstance(props, dict):
        return schema
    for arg_name, mapping in injected_args.items():
        if arg_name not in props:
            continue
        prop = props[arg_name]
        if not isinstance(prop, dict):
            continue
        prop[INJECTED_VAULT_KEY_PROP] = mapping.get("vault_key")
    return schema

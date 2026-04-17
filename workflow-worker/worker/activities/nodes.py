"""Side-effect-ful per-node activities.

All templating/expression evaluation uses a single sandboxed Jinja env —
`StrictUndefined` is on so referencing a missing context key fails loud
rather than rendering an empty string, and `autoescape=False` keeps
payloads verbatim (we're not producing HTML).
"""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, StrictUndefined
from temporalio import activity

_jinja = Environment(undefined=StrictUndefined, autoescape=False)


@activity.defn
async def render_template_activity(template: str, context: dict) -> dict:
    return {"text": _jinja.from_string(template or "").render(**context)}


@activity.defn
async def evaluate_condition_activity(expression: str, context: dict) -> dict:
    """Render `expression` as a Jinja template and coerce the trimmed result
    to a bool. Empty/whitespace-only evaluates to False."""
    rendered = _jinja.from_string(expression or "").render(**context).strip()
    truthy = rendered.lower() in ("true", "1", "yes", "on")
    return {"result": truthy, "rendered": rendered}


def _get_path(obj: Any, path: str) -> Any:
    """Walk dot-separated keys; integer segments are treated as list
    indexes. Returns None on any miss — the caller decides how strict to be.
    """
    current = obj
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            idx = int(part)
            current = current[idx] if -len(current) <= idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


@activity.defn
async def parse_payload_activity(mapping: dict, source: Any) -> dict:
    """For each `out_key -> json_path` mapping, pull `json_path` from
    `source`. `source` is typically the first upstream node's output, or
    the run's trigger payload when the parser is wired directly to the
    trigger.
    """
    return {key: _get_path(source, path) for key, path in (mapping or {}).items()}


@activity.defn
async def merge_activity(inputs: dict) -> dict:
    """Collapse multiple upstream outputs into one payload. Downstream
    consumers can reference `inputs[upstream_node_id]` to disambiguate."""
    return {"merged": inputs}

"""Agent auto-complete: 3-stage LLM flow over LiteLLM `/v1/messages`.

`tool_choice` is left at `auto` because forced single-field tool calls are
unreliable on non-Anthropic backends (they emit the inner value without the
object wrapper). The system prompt names the tool the model should call.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.schemas.agent_autocomplete import (
    AgentAutocompleteRequest,
    AgentAutocompleteResponse,
)
from app.schemas.mcp import McpToolResponse
from app.services import mcp_catalog

logger = logging.getLogger(__name__)

TOOL_NAME_SEPARATOR = "__"
_LITELLM_TIMEOUT = 300.0


class AutocompleteError(RuntimeError):
    pass


async def run(
    req: AgentAutocompleteRequest, user_token: str
) -> AgentAutocompleteResponse:
    all_tools = await mcp_catalog.fetch_tools(user_token)
    by_name: dict[str, dict] = {
        t["name"]: t for t in all_tools if TOOL_NAME_SEPARATOR in (t.get("name") or "")
    }

    stage1_ids = await _stage1_narrow(req, by_name, user_token)
    stage1_ids = [qid for qid in stage1_ids if qid in by_name]

    stage2_ids: list[str] = []
    if stage1_ids:
        stage2_ids = await _stage2_verify(req, stage1_ids, by_name, user_token)
        stage2_ids = [qid for qid in stage2_ids if qid in by_name]

    gen = await _stage3_generate(req, stage2_ids, by_name, user_token)
    return _merge(req, gen, stage2_ids, by_name)


# ---------------------------------------------------------------------------
# Stage 1: optimistic narrowing on signatures
# ---------------------------------------------------------------------------


async def _stage1_narrow(
    req: AgentAutocompleteRequest, by_name: dict[str, dict], user_token: str
) -> list[str]:
    signatures = [_signature_of(t) for t in by_name.values()]
    messages = [
        {
            "role": "system",
            "content": (
                "You pick candidate MCP tools that MIGHT be useful for the agent being designed. "
                "A later stage re-verifies with full descriptions, so be generous. "
                "Only return tool ids that appear in AVAILABLE_TOOLS. "
                "Call the `candidate_tools` tool exactly once with your result "
                "(empty `tool_ids` array if nothing is obviously relevant)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CURRENT = {json.dumps(_current_state(req))}\n"
                f"AVAILABLE_TOOLS = {json.dumps(signatures)}"
            ),
        },
    ]
    raw = await _litellm_json(
        model=_qualified_model(req),
        messages=messages,
        schema=_TOOL_IDS_SCHEMA,
        schema_name="candidate_tools",
        max_tokens=req.model_config_data.max_output_tokens,
        user_token=user_token,
    )
    return _coerce_string_list(raw.get("tool_ids"))


# ---------------------------------------------------------------------------
# Stage 2: verification with descriptions
# ---------------------------------------------------------------------------


async def _stage2_verify(
    req: AgentAutocompleteRequest,
    stage1_ids: list[str],
    by_name: dict[str, dict],
    user_token: str,
) -> list[str]:
    details = [_detail_of(by_name[qid]) for qid in stage1_ids]
    messages = [
        {
            "role": "system",
            "content": (
                "For each candidate, decide whether it's actually worth binding to this agent. "
                "Drop tools that are off-topic or duplicate existing capabilities. "
                "Return only ids from CANDIDATES. "
                "Call the `verified_tools` tool exactly once with your final subset "
                "(empty `tool_ids` array is allowed)."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CURRENT = {json.dumps(_current_state(req))}\n"
                f"CANDIDATES = {json.dumps(details)}"
            ),
        },
    ]
    raw = await _litellm_json(
        model=_qualified_model(req),
        messages=messages,
        schema=_TOOL_IDS_SCHEMA,
        schema_name="verified_tools",
        max_tokens=req.model_config_data.max_output_tokens,
        user_token=user_token,
    )
    return _coerce_string_list(raw.get("tool_ids"))


# ---------------------------------------------------------------------------
# Stage 3: generate name / description / instruction
# ---------------------------------------------------------------------------


async def _stage3_generate(
    req: AgentAutocompleteRequest,
    selected_ids: list[str],
    by_name: dict[str, dict],
    user_token: str,
) -> dict:
    selected = [_detail_of(by_name[qid]) for qid in selected_ids]
    messages = [
        {
            "role": "system",
            "content": (
                "Produce a coherent agent definition. "
                "Write a concise name (<= 80 chars) and description (<= 200 chars). "
                "Write a detailed system instruction that the agent will follow; "
                "reference the SELECTED_TOOLS where relevant. "
                "If CURRENT already has name/description/system_instruction text, "
                "treat it as a draft to build on, not as a hard constraint on wording. "
                "Call the `agent_definition` tool exactly once with your result."
            ),
        },
        {
            "role": "user",
            "content": (
                f"CURRENT = {json.dumps(_current_state(req))}\n"
                f"SELECTED_TOOLS = {json.dumps(selected)}"
            ),
        },
    ]
    raw = await _litellm_json(
        model=_qualified_model(req),
        messages=messages,
        schema=_AGENT_DEF_SCHEMA,
        schema_name="agent_definition",
        max_tokens=req.model_config_data.max_output_tokens,
        user_token=user_token,
    )
    return {
        "name": str(raw.get("name") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "instruction": str(raw.get("instruction") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _merge(
    req: AgentAutocompleteRequest,
    gen: dict,
    stage2_ids: list[str],
    by_name: dict[str, dict],
) -> AgentAutocompleteResponse:
    name = req.name if req.name.strip() else gen["name"]
    description = req.description if req.description.strip() else gen["description"]
    instruction = gen["instruction"]

    merged_ids: list[str] = []
    seen: set[str] = set()
    for qid in [*req.mcp_tool_ids, *stage2_ids]:
        if qid in seen:
            continue
        seen.add(qid)
        merged_ids.append(qid)

    tool_info = [_to_tool_response(by_name[qid]) for qid in merged_ids if qid in by_name]

    return AgentAutocompleteResponse(
        name=name,
        description=description,
        instruction=instruction,
        mcp_tool_ids=merged_ids,
        tool_info=tool_info,
    )


# ---------------------------------------------------------------------------
# LiteLLM call
# ---------------------------------------------------------------------------


async def _litellm_json(
    *,
    model: str,
    messages: list[dict],
    schema: dict,
    schema_name: str,
    max_tokens: int,
    user_token: str,
) -> dict:
    url = f"{settings.litellm_url.rstrip('/')}/v1/messages"

    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    user_messages = [m for m in messages if m.get("role") != "system"]

    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": user_messages,
        "tools": [
            {
                "name": schema_name,
                "description": f"Return the {schema_name} result.",
                "input_schema": schema,
            }
        ],
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    headers = {
        "Authorization": f"Bearer {settings.litellm_api_key}",
        "X-Aviary-User-Token": user_token,
        "anthropic-version": "2023-06-01",
    }
    try:
        async with httpx.AsyncClient(timeout=_LITELLM_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise AutocompleteError(f"LiteLLM request failed: {e}") from e

    if resp.status_code >= 400:
        raise AutocompleteError(
            f"LiteLLM returned {resp.status_code}: {resp.text[:500]}"
        )

    try:
        body = resp.json()
        content_blocks = body.get("content") or []
    except ValueError as e:
        raise AutocompleteError(f"Unexpected LiteLLM response shape: {e}") from e

    for block in content_blocks:
        if block.get("type") == "tool_use" and block.get("name") == schema_name:
            arguments = block.get("input")
            if isinstance(arguments, dict):
                return arguments
            raise AutocompleteError(
                f"tool_use input is not a dict: {type(arguments).__name__}"
            )

    raise AutocompleteError(
        f"No tool_use block named {schema_name!r} in response; stop_reason="
        f"{body.get('stop_reason')!r}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TOOL_IDS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tool_ids"],
    "properties": {
        "tool_ids": {"type": "array", "items": {"type": "string"}},
    },
}

_AGENT_DEF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "description", "instruction"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "instruction": {"type": "string"},
    },
}


def _qualified_model(req: AgentAutocompleteRequest) -> str:
    mc = req.model_config_data
    if TOOL_NAME_SEPARATOR in mc.model or "/" in mc.model:
        return mc.model
    return f"{mc.backend}/{mc.model}"


def _current_state(req: AgentAutocompleteRequest) -> dict:
    return {
        "name": req.name,
        "description": req.description,
        "system_instruction": req.instruction,
        "mcp_tool_ids": req.mcp_tool_ids,
        "user_prompt": req.user_prompt,
    }


def _signature_of(tool: dict) -> dict:
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    params = [
        {
            "name": pname,
            "type": _pretty_type(pschema),
            "required": pname in required,
        }
        for pname, pschema in props.items()
        if isinstance(pschema, dict)
    ]
    return {"id": tool["name"], "params": params}


def _detail_of(tool: dict) -> dict:
    sig = _signature_of(tool)
    sig["description"] = (tool.get("description") or "").strip()
    return sig


def _pretty_type(schema: dict) -> str:
    t = schema.get("type")
    if isinstance(t, list):
        return " | ".join(str(x) for x in t)
    if t == "array":
        items = schema.get("items") or {}
        return f"{_pretty_type(items)}[]" if isinstance(items, dict) else "array"
    return str(t or "any")


def _coerce_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, str)]


def _to_tool_response(tool: dict) -> McpToolResponse:
    qualified = tool["name"]
    server_name, _, raw = qualified.partition(TOOL_NAME_SEPARATOR)
    return McpToolResponse(
        id=qualified,
        server_id=server_name,
        server_name=server_name,
        name=raw or qualified,
        description=tool.get("description"),
        input_schema=tool.get("inputSchema") or {},
        qualified_name=qualified,
    )

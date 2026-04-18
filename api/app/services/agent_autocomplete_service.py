"""Agent auto-complete: 3-stage LLM flow via the supervisor.

Each stage registers a dedicated structured-output tool whose description
tells the CLI WHEN it should fire (e.g. "call this with the candidate
tool ids you picked"). The runtime binds the tool; we fish the
invocation out of `assembled_blocks` on the way back.
"""

from __future__ import annotations

import json
import logging

from app.schemas.agent_autocomplete import (
    AgentAutocompleteRequest,
    AgentAutocompleteResponse,
)
from app.schemas.mcp import McpToolResponse
from app.services import llm_runtime, mcp_catalog

logger = logging.getLogger(__name__)

TOOL_NAME_SEPARATOR = "__"


class AutocompleteError(RuntimeError):
    pass


_CANDIDATE_TOOL = {
    "name": "report_candidate_tools",
    "description": (
        "Call this once with the MCP tool ids you think MIGHT be useful for "
        "the agent being designed. Be generous — a later stage re-verifies. "
        "Pass an empty list if none apply."
    ),
    "fields": [
        {
            "name": "tool_ids",
            "type": "list",
            "description": "Chosen MCP tool identifiers (exact, from AVAILABLE_TOOLS).",
        },
    ],
}

_VERIFY_TOOL = {
    "name": "report_verified_tools",
    "description": (
        "Call this once with the final subset of candidate MCP tools that "
        "are actually worth binding to this agent. Empty list is allowed."
    ),
    "fields": [
        {
            "name": "tool_ids",
            "type": "list",
            "description": "Final subset (exact ids, from CANDIDATES).",
        },
    ],
}

_AGENT_DEF_TOOL = {
    "name": "fill_agent_fields",
    "description": (
        "Call this once with the generated agent definition — name, short "
        "description, and detailed system instruction. The caller will "
        "auto-fill these into the agent form."
    ),
    "fields": [
        {"name": "name", "type": "str", "description": "Concise agent name (<= 80 chars)."},
        {"name": "description", "type": "str", "description": "One-line summary (<= 200 chars)."},
        {"name": "instruction", "type": "str", "description": "Detailed system instruction the agent will follow."},
    ],
}


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
    system = (
        "You pick candidate MCP tools that MIGHT be useful for the agent being designed. "
        "A later stage re-verifies with full descriptions, so be generous. "
        "Only return tool ids that appear in AVAILABLE_TOOLS.\n\n"
        + _format_tool_call_instruction(_CANDIDATE_TOOL)
    )
    user_message = (
        f"CURRENT = {json.dumps(_current_state(req))}\n"
        f"AVAILABLE_TOOLS = {json.dumps(signatures)}"
    )
    raw = await _call(req, system, user_message, _CANDIDATE_TOOL, user_token)
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
    system = (
        "For each candidate, decide whether it's actually worth binding to this agent. "
        "Drop tools that are off-topic or duplicate existing capabilities. "
        "Return only ids from CANDIDATES.\n\n"
        + _format_tool_call_instruction(_VERIFY_TOOL)
    )
    user_message = (
        f"CURRENT = {json.dumps(_current_state(req))}\n"
        f"CANDIDATES = {json.dumps(details)}"
    )
    raw = await _call(req, system, user_message, _VERIFY_TOOL, user_token)
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
    system = (
        "Produce a coherent agent definition. "
        "Write a concise name (<= 80 chars) and description (<= 200 chars). "
        "Write a detailed system instruction that the agent will follow; "
        "reference the SELECTED_TOOLS where relevant. "
        "If CURRENT already has name/description/system_instruction text, "
        "treat it as a draft to build on, not as a hard constraint on wording.\n\n"
        + _format_tool_call_instruction(_AGENT_DEF_TOOL)
    )
    user_message = (
        f"CURRENT = {json.dumps(_current_state(req))}\n"
        f"SELECTED_TOOLS = {json.dumps(selected)}"
    )
    raw = await _call(req, system, user_message, _AGENT_DEF_TOOL, user_token)
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
# Supervisor-backed call
# ---------------------------------------------------------------------------


async def _call(
    req: AgentAutocompleteRequest,
    system: str,
    user_message: str,
    tool: dict,
    user_token: str,
) -> dict:
    mc = req.model_config_json
    runtime_model_config: dict = {
        "backend": mc.backend,
        "model": mc.model,
        "max_output_tokens": mc.max_output_tokens,
    }
    try:
        result = await llm_runtime.run_once(
            model_config=runtime_model_config,
            system=system,
            user_message=user_message,
            structured_outputs=[tool],
            user_token=user_token,
        )
    except llm_runtime.LLMRuntimeError as e:
        raise AutocompleteError(str(e)) from e

    block = llm_runtime.find_structured_tool_call(result, tool["name"])
    if block is None:
        raise AutocompleteError(
            f"Model did not call {tool['name']!r}; assembled_text="
            f"{(result.get('assembled_text') or '')[:200]!r}"
        )
    payload = block.get("input")
    if not isinstance(payload, dict):
        raise AutocompleteError(
            f"{tool['name']} input is not a dict: {type(payload).__name__}"
        )
    return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_tool_call_instruction(tool: dict) -> str:
    lines = [
        f"Call the `mcp__aviary_output__{tool['name']}` tool exactly once with the following fields:",
    ]
    for f in tool["fields"]:
        t = "array of strings" if f["type"] == "list" else "string"
        desc = f" — {f['description']}" if f.get("description") else ""
        lines.append(f"- `{f['name']}` ({t}){desc}")
    return "\n".join(lines)


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

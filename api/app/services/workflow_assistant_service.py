"""Workflow Builder AI Assistant — three LLM calls against the workflow's
default model, no fallback, no retries.

1. Shortlist — compact signatures only, model returns candidate ids.
2. Narrow — descriptions included, model picks the actual set.
3. Plan — narrowed catalog fed into the plan-generation system prompt.

All three calls share the same token budget; that's the only knob.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import HTTPException, status
from pydantic import TypeAdapter, ValidationError

from app.config import settings
from app.db.models import Workflow
from app.schemas.workflow_assistant import (
    PlanOp,
    WorkflowAssistantRequest,
    WorkflowAssistantResponse,
)
from app.services import mcp_catalog

logger = logging.getLogger(__name__)

_plan_adapter: TypeAdapter[list[PlanOp]] = TypeAdapter(list[PlanOp])

_HISTORY_CAP = 10
_DESCRIPTION_CAP = 400
_MAX_TOKENS = 16384


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def ask(
    workflow: Workflow,
    body: WorkflowAssistantRequest,
    user_token: str,
) -> WorkflowAssistantResponse:
    model_cfg = workflow.model_config_json or {}
    backend = model_cfg.get("backend")
    model = model_cfg.get("model")
    if not backend or not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow has no default model configured",
        )
    model_name = model if "/" in model else f"{backend}/{model}"

    selected_tools = await _select_relevant_tools(
        user_message=body.user_message,
        history=body.history,
        current_definition=body.current_definition,
        model_name=model_name,
        user_token=user_token,
    )

    plan, reply = await _generate_plan(
        user_message=body.user_message,
        history=body.history,
        current_definition=body.current_definition,
        selected_tools=selected_tools,
        model_name=model_name,
        user_token=user_token,
    )

    err = _validate_plan_references(plan, body.current_definition)
    if err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM plan failed reference validation: {err}",
        )
    _inject_workflow_defaults(plan, backend=backend, model=model)

    return WorkflowAssistantResponse(reply=reply, plan=plan)


# ---------------------------------------------------------------------------
# LiteLLM JSON call
# ---------------------------------------------------------------------------


async def _litellm_json(
    *,
    model_name: str,
    user_token: str,
    messages: list[dict],
) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.litellm_api_key}",
        "X-Aviary-User-Token": user_token,
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "max_tokens": _MAX_TOKENS,
    }

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{settings.litellm_url}/chat/completions",
            headers=headers, json=payload,
        )

    if resp.status_code >= 400:
        logger.warning("LiteLLM %s: %s", resp.status_code, resp.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway error ({resp.status_code})",
        )

    raw = resp.json()["choices"][0]["message"]["content"]
    if not isinstance(raw, str) or not raw.strip():
        logger.warning("LLM empty content (model=%s): %r", model_name, resp.json().get("choices"))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM returned empty content",
        )
    try:
        return json.loads(_extract_json_object(raw))
    except json.JSONDecodeError as e:
        logger.warning("LLM non-JSON (model=%s): %r", model_name, raw[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned non-JSON: {e}",
        ) from e


# ---------------------------------------------------------------------------
# Stages 1 + 2: tool shortlisting
# ---------------------------------------------------------------------------


_STAGE1_SYSTEM = """\
You are picking MCP tools that MIGHT be relevant to a user's workflow request.

You will see:
- The user's request (+ prior conversation)
- The current workflow state
- A list of tool identifiers in the form "{server}__{tool}" — NO descriptions

Return EXACTLY this JSON shape (no markdown fences, no extra keys):
{"candidate_tool_ids": ["server1__tool1", "server2__tool2"]}

Err on the side of inclusion (up to ~20 candidates). If nothing applies,
return {"candidate_tool_ids": []}. Do NOT invent identifiers — only
pick from the list.
"""

_STAGE2_SYSTEM = """\
You are narrowing a shortlist of MCP tools to the ones actually needed for
the user's workflow request.

You will see:
- The user's request (+ prior conversation)
- The current workflow state
- A shortlist of tools with their full descriptions

Return EXACTLY this JSON shape (no markdown fences, no extra keys):
{"selected_tool_ids": ["server1__tool1", "server2__tool2"]}

Pick only what's clearly useful. If nothing applies, return
{"selected_tool_ids": []}. Do NOT invent identifiers.
"""


async def _select_relevant_tools(
    *,
    user_message: str,
    history,
    current_definition: dict,
    model_name: str,
    user_token: str,
) -> list[dict]:
    catalog = await mcp_catalog.fetch_tools(user_token)
    if not catalog:
        return []

    # Stage 1: signatures only.
    stage1 = await _litellm_json(
        model_name=model_name,
        user_token=user_token,
        messages=_build_history_messages(
            system=(
                _STAGE1_SYSTEM
                + _format_context_block(current_definition)
                + "\n## Available tool ids\n"
                + "\n".join(f"- {t['name']}" for t in catalog)
            ),
            history=history,
            user_message=user_message,
        ),
    )
    if not isinstance(stage1, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stage-1 expected JSON object, got {type(stage1).__name__}",
        )
    valid = {t["name"] for t in catalog}
    candidates = [c for c in stage1.get("candidate_tool_ids", []) if c in valid]
    if not candidates:
        return []

    # Stage 2: descriptions included.
    by_name = {t["name"]: t for t in catalog}
    detailed_block = "\n".join(
        f"- {name}: {(by_name[name].get('description') or '(no description)')[:_DESCRIPTION_CAP]}"
        for name in candidates
    )
    stage2 = await _litellm_json(
        model_name=model_name,
        user_token=user_token,
        messages=_build_history_messages(
            system=(
                _STAGE2_SYSTEM
                + _format_context_block(current_definition)
                + "\n## Candidate tools\n"
                + detailed_block
            ),
            history=history,
            user_message=user_message,
        ),
    )
    if not isinstance(stage2, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Stage-2 expected JSON object, got {type(stage2).__name__}",
        )
    candidate_set = set(candidates)
    selected = [s for s in stage2.get("selected_tool_ids", []) if s in candidate_set]
    return [by_name[name] for name in selected]


# ---------------------------------------------------------------------------
# Stage 3: plan generation
# ---------------------------------------------------------------------------


_PLAN_SYSTEM = """\
You are the Aviary Workflow Builder assistant. You help a user modify a
visual workflow (a DAG of nodes and edges) by returning a JSON plan of
edit operations.

## Node types and required `data` fields
- manual_trigger: { "label": string }
- webhook_trigger: { "label": string, "path": string }
- agent_step: {
    "label": string,
    "instruction": string,
    "mcp_tool_ids": string[],     // bind tools from the list below if needed
    "prompt_template": string     // use "{{input}}" for upstream data
  }
  NOTE: DO NOT emit `model_config` for agent_step. The workflow's
  default backend/model is injected automatically on the server.
- condition: { "label": string, "expression": string }
- merge: { "label": string }
- payload_parser: { "label": string, "mapping": object }
- template: { "label": string, "template": string }

## Output format
Return a SINGLE JSON object with exactly two keys:
- "reply": short natural-language message shown to the user
- "plan": ordered array of edit operations

## Operation vocabulary
{ "op": "add_node", "id": "<new_unique_id>", "type": "<node_type>",
  "position": { "x": <number>, "y": <number> }, "data": { ... } }
{ "op": "update_node", "id": "<existing_id>", "data_patch": { ... } }
{ "op": "delete_node", "id": "<existing_id>" }
{ "op": "add_edge", "source": "<node_id>", "target": "<node_id>" }
{ "op": "delete_edge", "id": "<existing_edge_id>" }

## Rules
1. Emit operations in dependency order. add_node must come BEFORE any
   add_edge that references it.
2. New node ids must be unique across both the current state AND the plan.
   Use descriptive snake_case ids (e.g. "summarize_step").
3. add_edge source/target must resolve to ids that exist after the
   preceding operations (existing nodes or newly added ones, not deleted).
4. DO NOT re-emit nodes the user did not ask to change — emit only deltas.
5. Place new nodes at readable positions (~200px spacing from related
   existing nodes, growing left-to-right or top-to-bottom).
6. For a pure question, return "plan": [] and put the answer in "reply".
7. For an ambiguous request, ask a clarifying question and return empty plan.
8. Output raw JSON only. No markdown fences, no prose outside the JSON.
9. Every workflow needs exactly one trigger node unless the user is
   building pieces incrementally.
10. On agent_step, only bind tools from the "Available MCP tools" list
    below. If no tools are listed, leave "mcp_tool_ids": [].
"""


async def _generate_plan(
    *,
    user_message: str,
    history,
    current_definition: dict,
    selected_tools: list[dict],
    model_name: str,
    user_token: str,
) -> tuple[list[PlanOp], str]:
    system = (
        _PLAN_SYSTEM
        + _format_context_block(current_definition)
        + _format_tools_block(selected_tools)
    )
    parsed = await _litellm_json(
        model_name=model_name,
        user_token=user_token,
        messages=_build_history_messages(
            system=system, history=history, user_message=user_message,
        ),
    )

    reply = parsed.get("reply", "")
    if not isinstance(reply, str):
        reply = str(reply)

    plan_raw = parsed.get("plan", [])
    if not isinstance(plan_raw, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM plan must be a list",
        )

    try:
        plan = _plan_adapter.validate_python(plan_raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM plan failed schema validation: {e.errors()}",
        ) from e

    return plan, reply


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _build_history_messages(
    *, system: str, history, user_message: str,
) -> list[dict]:
    msgs: list[dict] = [{"role": "system", "content": system}]
    for turn in history[-_HISTORY_CAP:]:
        msgs.append({"role": turn.role, "content": turn.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


def _format_context_block(current_definition: dict) -> str:
    state = json.dumps(
        {
            "nodes": current_definition.get("nodes", []),
            "edges": current_definition.get("edges", []),
        },
        ensure_ascii=False,
    )
    return f"\n## Current workflow state\n{state}"


def _format_tools_block(selected_tools: list[dict]) -> str:
    if not selected_tools:
        return "\n## Available MCP tools\n(none — do not bind any tool ids)"
    lines = ["\n## Available MCP tools"]
    for t in selected_tools:
        desc = (t.get("description") or "(no description)")[:_DESCRIPTION_CAP]
        lines.append(f"- {t['name']}: {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def _inject_workflow_defaults(plan: list[PlanOp], backend: str, model: str) -> None:
    """Every assistant-created agent_step runs with the workflow's default
    backend/model.
    """
    default_cfg = {"backend": backend, "model": model}
    for op in plan:
        if op.op == "add_node" and op.type == "agent_step":
            op.data["model_config"] = dict(default_cfg)


# ---------------------------------------------------------------------------
# JSON extraction + reference validation
# ---------------------------------------------------------------------------


def _extract_json_object(text: str) -> str:
    """Pull the first top-level {...} out of LLM output, stripping markdown
    fences and surrounding commentary.
    """
    s = text.strip()

    if s.startswith("```"):
        newline = s.find("\n")
        if newline != -1:
            s = s[newline + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()

    start = s.find("{")
    if start < 0:
        return s

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return s[start:]


def _validate_plan_references(plan: list[PlanOp], definition: dict) -> str | None:
    nodes_raw = definition.get("nodes", [])
    edges_raw = definition.get("edges", [])

    live_nodes: set[str] = {
        n["id"] for n in nodes_raw if isinstance(n, dict) and isinstance(n.get("id"), str)
    }
    live_edges: set[str] = {
        e["id"] for e in edges_raw if isinstance(e, dict) and isinstance(e.get("id"), str)
    }

    for i, op in enumerate(plan):
        if op.op == "add_node":
            if op.id in live_nodes:
                return f"step[{i}] add_node id '{op.id}' conflicts with existing node"
            live_nodes.add(op.id)
        elif op.op == "update_node":
            if op.id not in live_nodes:
                return f"step[{i}] update_node id '{op.id}' does not exist"
        elif op.op == "delete_node":
            if op.id not in live_nodes:
                return f"step[{i}] delete_node id '{op.id}' does not exist"
            live_nodes.discard(op.id)
        elif op.op == "add_edge":
            if op.source not in live_nodes:
                return f"step[{i}] add_edge source '{op.source}' does not exist"
            if op.target not in live_nodes:
                return f"step[{i}] add_edge target '{op.target}' does not exist"
            if op.id:
                if op.id in live_edges:
                    return f"step[{i}] add_edge id '{op.id}' conflicts"
                live_edges.add(op.id)
        elif op.op == "delete_edge":
            if op.id not in live_edges:
                return f"step[{i}] delete_edge id '{op.id}' does not exist"
            live_edges.discard(op.id)
    return None

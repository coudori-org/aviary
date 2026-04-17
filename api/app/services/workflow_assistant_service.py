"""Workflow Builder AI Assistant.

Calls LiteLLM directly (not via supervisor) with the workflow's default
model, asking the LLM to return an ordered JSON plan of edit operations.
The plan is validated server-side for schema + reference integrity, then
shipped to the frontend which applies it atomically.
"""

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

logger = logging.getLogger(__name__)

_plan_adapter: TypeAdapter[list[PlanOp]] = TypeAdapter(list[PlanOp])

_HISTORY_CAP = 10

_SYSTEM_PROMPT = """\
You are the Aviary Workflow Builder assistant. You help a user modify a
visual workflow (a DAG of nodes and edges) by returning a JSON plan of
edit operations.

## Node types and required `data` fields
- manual_trigger: { "label": string }
- webhook_trigger: { "label": string, "path": string }
- agent_step: {
    "label": string,
    "instruction": string,
    "mcp_tool_ids": string[],     // leave empty []; user picks tools in the UI
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
   Use descriptive snake_case ids (e.g. "summarize_step", "route_by_sentiment").
3. add_edge source/target must resolve to ids that exist after the
   preceding operations (existing nodes or newly added ones, not deleted).
4. DO NOT re-emit nodes the user did not ask to change. Emit only the
   deltas needed.
5. Place new nodes at readable positions (~200px spacing from related
   existing nodes, growing left-to-right or top-to-bottom).
6. For a pure question (no edits), return "plan": [] and put the answer
   in "reply".
7. For an ambiguous request, ask a clarifying question in "reply" and
   return "plan": [].
8. Output raw JSON only. No markdown fences, no prose outside the JSON.
9. Every workflow needs exactly one trigger node (manual_trigger or
   webhook_trigger) as the entry point unless the user is building
   pieces incrementally.
"""


def _build_system_prompt(current_definition: dict) -> str:
    state_json = json.dumps(
        {
            "nodes": current_definition.get("nodes", []),
            "edges": current_definition.get("edges", []),
        },
        ensure_ascii=False,
    )
    return f"{_SYSTEM_PROMPT}\n## Current workflow state\n{state_json}"


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

    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt(body.current_definition)},
    ]
    for turn in body.history[-_HISTORY_CAP:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": body.user_message})

    payload = {
        "model": model_name,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": model_cfg.get("max_output_tokens") or 4096,
    }
    headers = {
        "Authorization": f"Bearer {settings.litellm_api_key}",
        "X-Aviary-User-Token": user_token,
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.litellm_url}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as e:
        logger.warning("LiteLLM request failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway unreachable: {e}",
        ) from e

    if resp.status_code >= 400:
        logger.warning(
            "LiteLLM returned %s for workflow=%s: %s",
            resp.status_code, workflow.id, resp.text[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway error ({resp.status_code})",
        )

    try:
        raw_content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected LLM response shape: {e}",
        ) from e

    json_text = _extract_json_object(raw_content)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.warning(
            "LLM returned non-JSON content for workflow=%s: %r",
            workflow.id, raw_content[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM returned non-JSON content: {e}. Preview: {raw_content[:200]!r}",
        ) from e

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

    err = _validate_plan_references(plan, body.current_definition)
    if err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM plan failed reference validation: {err}",
        )

    _inject_workflow_defaults(plan, backend=backend, model=model)

    return WorkflowAssistantResponse(reply=reply, plan=plan)


def _inject_workflow_defaults(plan: list[PlanOp], backend: str, model: str) -> None:
    """Force agent_step nodes created by the assistant to use the
    workflow's default backend/model. The LLM is instructed to omit
    model_config entirely; we fill it in here so no step runs against
    a stale/invalid model the user never chose.
    """
    default_cfg = {"backend": backend, "model": model}
    for op in plan:
        if op.op == "add_node" and op.type == "agent_step":
            op.data["model_config"] = dict(default_cfg)


def _extract_json_object(text: str) -> str:
    """Extract a single JSON object from LLM output.

    LLMs frequently wrap JSON in markdown code fences or prepend/append
    commentary even when asked not to. Strip fences, then walk the
    string tracking brace depth (ignoring braces inside string literals)
    to pull out the first top-level {...} block.
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

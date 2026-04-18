"""Workflow Builder AI Assistant — a conversational chat riding the
supervisor→runtime pipeline.

One LLM call per user message. The runtime binds a single dynamic tool
(`apply_workflow_plan`) via `structured_outputs[]`; the CLI decides
whether to call it. Regular chat-reply text and the optional tool call
both land in `assembled_blocks`, which we splice into the response
shape the frontend already understands (`{reply, plan}`).
"""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException, status
from pydantic import TypeAdapter, ValidationError

from app.db.models import Workflow
from app.schemas.workflow_assistant import (
    PlanOp,
    WorkflowAssistantRequest,
    WorkflowAssistantResponse,
)
from app.services import llm_runtime, mcp_catalog

logger = logging.getLogger(__name__)

_plan_adapter: TypeAdapter[list[PlanOp]] = TypeAdapter(list[PlanOp])

_HISTORY_CAP = 10
_DESCRIPTION_CAP = 300


_APPLY_WORKFLOW_PLAN_TOOL = {
    "name": "apply_workflow_plan",
    "description": (
        "Call this tool WHEN AND ONLY WHEN the user's latest message is an "
        "actionable request to modify the workflow (add / update / delete "
        "nodes or edges). The UI will show the user an accept/deny card for "
        "the plan; if accepted, the operations will be applied to the DAG. "
        "For questions, clarifications, or anything that doesn't need a "
        "workflow change, DO NOT call this tool — just reply with plain "
        "text as a regular chat assistant would."
    ),
    "fields": [
        {
            "name": "plan_json",
            "type": "str",
            "description": (
                "JSON-encoded array of edit operations. Must be a valid JSON "
                "array of objects. See the Plan Operations section of the "
                "system prompt for the exact shape. Use \"[]\" ONLY if you're "
                "confident no edit is needed (but then prefer not calling "
                "this tool at all)."
            ),
        },
    ],
}

_APPLY_WORKFLOW_PLAN_CLI_NAME = llm_runtime.structured_tool_cli_name(
    _APPLY_WORKFLOW_PLAN_TOOL["name"],
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def ask(
    workflow: Workflow,
    body: WorkflowAssistantRequest,
    user_token: str,
    session_id: str | None = None,
) -> WorkflowAssistantResponse:
    model_cfg = workflow.model_config_json or {}
    backend = model_cfg.get("backend")
    model = model_cfg.get("model")
    if not backend or not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow has no default model configured",
        )
    runtime_model_config = {"backend": backend, "model": model}
    if isinstance(model_cfg.get("max_output_tokens"), int):
        runtime_model_config["max_output_tokens"] = model_cfg["max_output_tokens"]

    catalog = await mcp_catalog.fetch_tools(user_token)

    system = _build_system_prompt(
        current_definition=body.current_definition,
        catalog=catalog,
    )
    history_turns = [
        {"role": turn.role, "content": turn.content}
        for turn in (body.history or [])[-_HISTORY_CAP:]
    ]

    try:
        result = await llm_runtime.run_once(
            model_config=runtime_model_config,
            system=system,
            user_message=body.user_message,
            structured_outputs=[_APPLY_WORKFLOW_PLAN_TOOL],
            history_turns=history_turns,
            user_token=user_token,
            session_id=session_id,
        )
    except llm_runtime.LLMRuntimeError as e:
        logger.warning("Workflow assistant LLM call failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM gateway error: {e}",
        ) from e

    reply = result.get("assembled_text") or ""
    plan = _extract_plan(result)

    if plan:
        err = _validate_plan_references(plan, body.current_definition)
        if err:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM plan failed reference validation: {err}",
            )
        _inject_workflow_defaults(plan, backend=backend, model=model)

    return WorkflowAssistantResponse(reply=reply, plan=plan)


# ---------------------------------------------------------------------------
# Plan extraction
# ---------------------------------------------------------------------------


def _extract_plan(result: dict) -> list[PlanOp]:
    block = llm_runtime.find_tool_call(result, _APPLY_WORKFLOW_PLAN_CLI_NAME)
    if block is None:
        return []
    payload = block.get("input")
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"apply_workflow_plan input is not a dict: {type(payload).__name__}",
        )
    plan_json = payload.get("plan_json", "[]")
    if not isinstance(plan_json, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"plan_json must be a string, got {type(plan_json).__name__}",
        )
    try:
        plan_raw = json.loads(plan_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"plan_json is not valid JSON: {e}",
        ) from e
    if not isinstance(plan_raw, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="plan_json must decode to a list",
        )
    try:
        return _plan_adapter.validate_python(plan_raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM plan failed schema validation: {e.errors()}",
        ) from e


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


_ROLE_BLOCK = """\
You are the Aviary Workflow Builder Assistant — a helpful, friendly
co-pilot embedded in a visual workflow editor. Users build automations
by wiring nodes in a DAG; you help them reason about, plan, and edit
those workflows.

## Your two modes
1. **Chat** — the default. Answer questions, explain nodes / operations /
   MCP tools, discuss ideas, ask clarifying questions. Respond in plain
   conversational text. Be concise (1–4 short paragraphs max).
2. **Edit** — when the user clearly asks you to change the workflow
   (add / update / remove nodes or edges), call the
   `mcp__aviary_output__apply_workflow_plan` tool with a `plan_json`
   string. The UI renders an accept/deny card for the plan; don't apply
   anything yourself. A short text reply accompanying the tool call is
   fine (e.g. "Here's what I'll change:") but not required.

If a request is ambiguous, stay in Chat mode and ask.

## Node types and required `data` fields
- manual_trigger: { "label": string }
- webhook_trigger: { "label": string, "path": string }
- agent_step: {
    "label": string,
    "instruction": string,
    "mcp_tool_ids": string[],          // bind tools from the catalog below
    "prompt_template": string,         // use "{{input}}" for upstream data
    "structured_output_fields"?: [     // OPTIONAL — see "Structured output"
      { "name": string, "type": "str" | "list", "description"?: string }
    ],
    "artifacts"?: [                    // OPTIONAL — see "Artifacts"
      { "name": string, "description"?: string }
    ]
  }
  NOTE: DO NOT emit `model_config` for agent_step. The workflow's default
  backend/model is injected automatically on the server.
- condition: { "label": string, "expression": string }
- merge: { "label": string }
- payload_parser: { "label": string, "mapping": object }
- template: { "label": string, "template": string }

## Structured output (agent_step only)
Every agent_step ALREADY emits `{ "text": "..." }` as its output — `text`
is the step's final user-facing response and is always present. Downstream
nodes reference it as `{{ input.text }}`.

Use `structured_output_fields` to (a) customize how the agent writes the
`text` field, and/or (b) ADD more named fields when downstream nodes need
to branch on or format individual pieces of the agent's answer. Rules:
- To customize the default `text` output, prepend a `{ "name": "text",
  "type": "str", "description": "..." }` entry (name/type locked).
- For extra fields: lowercase snake_case, `type: "str" | "list"`,
  `description` strongly recommended. Keep the list short (≤4 extras).
- Reference fields downstream as `{{ input.<name> }}` (single-upstream)
  or `{{ inputs.<node_id>.<name> }}` (multi-upstream).

## Artifacts (agent_step only)
Use `artifacts` when a step produces a FILE or DIRECTORY that downstream
steps need to consume — code, reports, built assets, scraped data, etc.
Each entry is `{ "name": string, "description"?: string }`. The runtime
exposes `save_as_artifact` to the agent; the agent chooses which of its
working files match which artifact (the description guides this choice).
Downstream nodes whose upstream produced an artifact see it pre-copied at
`/workspace/{name}` inside the sandbox. Rules:
- Artifact names are lowercase snake_case and should describe the content,
  not the filename (e.g. `report`, `parsed_data`, `build_output`).
- Only declare artifacts when a file hand-off is actually needed; for
  textual / structured data prefer `structured_output_fields`.
- When a downstream step has multiple upstreams producing artifacts, their
  `name`s must not collide — plan accordingly.

## Plan operations (items of `plan_json`, which is a JSON-encoded array)
{ "op": "add_node", "id": "<new_unique_id>", "type": "<node_type>",
  "position": { "x": <number>, "y": <number> }, "data": { ... } }
{ "op": "update_node", "id": "<existing_id>", "data_patch": { ... } }
{ "op": "delete_node", "id": "<existing_id>" }
{ "op": "add_edge", "source": "<node_id>", "target": "<node_id>" }
{ "op": "delete_edge", "id": "<existing_edge_id>" }

## Rules for plans
1. Emit operations in dependency order. add_node must come BEFORE any
   add_edge that references it.
2. New node ids must be unique across both the current state AND the plan.
   Use descriptive snake_case ids (e.g. "summarize_step").
3. add_edge source/target must resolve to ids that exist after the
   preceding operations.
4. DO NOT re-emit nodes the user did not ask to change — emit only deltas.
5. Place new nodes at readable positions (~200px spacing).
6. Every workflow needs exactly one trigger node (unless the user is
   building incrementally and has said so).
7. On agent_step, only bind tools from the "Available MCP tools" catalog
   below. If the catalog is empty, leave `mcp_tool_ids: []`.
"""


def _build_system_prompt(current_definition: dict, catalog: list[dict]) -> str:
    return (
        _ROLE_BLOCK
        + _format_context_block(current_definition)
        + _format_tools_block(catalog)
    )


def _format_context_block(current_definition: dict) -> str:
    state = json.dumps(
        {
            "nodes": current_definition.get("nodes", []),
            "edges": current_definition.get("edges", []),
        },
        ensure_ascii=False,
    )
    return f"\n\n## Current workflow state\n{state}"


def _format_tools_block(catalog: list[dict]) -> str:
    if not catalog:
        return "\n\n## Available MCP tools\n(none — leave `mcp_tool_ids: []`)"
    lines = ["\n\n## Available MCP tools"]
    for t in catalog:
        name = t.get("name")
        if not name:
            continue
        desc = (t.get("description") or "").strip()
        if desc:
            desc = desc[:_DESCRIPTION_CAP]
            lines.append(f"- {name}: {desc}")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


def _inject_workflow_defaults(plan: list[PlanOp], backend: str, model: str) -> None:
    default_cfg = {"backend": backend, "model": model}
    for op in plan:
        if op.op == "add_node" and op.type == "agent_step":
            op.data["model_config"] = dict(default_cfg)


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

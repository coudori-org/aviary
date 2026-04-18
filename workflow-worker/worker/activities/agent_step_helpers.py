"""Pure helpers for agent_step — request building + result extraction.

Kept activity-free so the orchestration activity stays focused on side
effects (DB, Redis, supervisor stream) and these can be unit-tested
without a Temporal worker context.
"""

from __future__ import annotations

import uuid

from worker.template import jinja_env


_ALLOWED_FIELD_TYPES = {"str", "list"}
_DEFAULT_TEXT_DESCRIPTION = (
    "The final user-facing response text for this step — a concise summary "
    "of the agent's answer."
)
_OUTPUT_TOOL_NAME = "emit_final_response"
_OUTPUT_TOOL_DESCRIPTION = (
    "Emit the final structured response for this workflow step. Call this "
    "exactly once, as your last action, with every field populated."
)
_ARTIFACT_TOOL_CLI_NAME = "mcp__aviary_artifacts__save_as_artifact"

# Hard ceiling on assistant turns per step — protects against local-model
# verify loops where the model keeps inspecting its own output after
# emitting the final response.
AGENT_STEP_MAX_TURNS = 15


def step_session_id(run_id: str, node_id: str, root_run_id: str | None = None) -> str:
    """Deterministic per-(chain, node) session UUID.

    Anchored on the resume chain's **root** run so every run in the chain
    resolves the same node to the same session — a resumed run can render
    its carried-over step's chat transcript instead of 404-ing on a
    session that only exists under the original run's id.

    uuid5 means the orchestrator can compute it without touching the DB
    (used to surface the id on node_status events before the activity
    runs)."""
    anchor = root_run_id or run_id
    return str(uuid.uuid5(uuid.UUID(anchor), node_id))


def render_prompt(template: str, *, input_value, inputs: dict, trigger_data: dict) -> str:
    return jinja_env.from_string(template or "").render(
        input=input_value, inputs=inputs, trigger=trigger_data,
    )


def build_output_tool(raw: list) -> dict:
    """Normalise `structured_output_fields` into a structured_outputs[] entry.

    A single `text` entry in `raw` overrides the default description only
    (name/type stay locked). Other entries become extras after name /
    type / duplicate validation.
    """
    text_desc = _DEFAULT_TEXT_DESCRIPTION
    extras: list[dict] = []
    seen: set[str] = {"text"}
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if name == "text":
            desc = item.get("description")
            if isinstance(desc, str) and desc.strip():
                text_desc = desc.strip()
            continue
        if name in seen:
            continue
        ftype = item.get("type")
        if ftype not in _ALLOWED_FIELD_TYPES:
            continue
        entry: dict = {"name": name, "type": ftype}
        desc = item.get("description")
        if isinstance(desc, str) and desc.strip():
            entry["description"] = desc.strip()
        extras.append(entry)
        seen.add(name)

    return {
        "name": _OUTPUT_TOOL_NAME,
        "description": _OUTPUT_TOOL_DESCRIPTION,
        "fields": [
            {"name": "text", "type": "str", "description": text_desc},
            *extras,
        ],
    }


def normalize_artifacts(raw: list) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        if name in seen:
            continue
        desc = item.get("description")
        entry: dict = {"name": name}
        if isinstance(desc, str) and desc.strip():
            entry["description"] = desc.strip()
        out.append(entry)
        seen.add(name)
    return out


def collect_input_artifacts(inputs: dict) -> list[dict]:
    """Flatten upstream ``artifacts_produced`` entries. Used by the runtime
    to pre-copy files into ``/workspace`` before the SDK starts."""
    out: list[dict] = []
    for src_id, payload in (inputs or {}).items():
        if not isinstance(payload, dict):
            continue
        produced = payload.get("artifacts_produced")
        if not isinstance(produced, list):
            continue
        for entry in produced:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name:
                out.append({"upstream_node_id": src_id, "artifact_name": name})
    return out


def augment_instruction(
    instruction: str, output_tool: dict, artifacts: list[dict], input_artifacts: list[dict],
) -> str:
    """Append final-response + artifacts guidance so the model consistently
    calls the registered tools instead of emitting plain-text answers."""
    lines = ["", "## Final response"]
    lines.append(
        f"Emit your final answer by calling the "
        f"`mcp__aviary_output__{output_tool['name']}` tool exactly once, at "
        f"the very end of your work. The tool call IS the response — do not "
        f"also write it as plain text."
    )
    lines.append("")
    lines.append("Fields:")
    for f in output_tool["fields"]:
        t = "array of strings" if f["type"] == "list" else "string"
        desc = f" — {f['description']}" if f.get("description") else ""
        lines.append(f"- `{f['name']}` ({t}){desc}")
    lines.append("")
    lines.append(
        "**Stop rule (important):** Immediately after the "
        f"`mcp__aviary_output__{output_tool['name']}` tool call completes, "
        "END YOUR TURN. Do not run any more tools, do not re-read or "
        "re-verify files, do not list directories, do not add a closing "
        "message. The tool result text (\"recorded.\") is just an "
        "acknowledgement; it is NOT a request for further action."
    )

    if artifacts or input_artifacts:
        lines.extend(["", "## Artifacts"])
        if input_artifacts:
            lines.append("Upstream artifacts have been copied into your working directory:")
            for ia in input_artifacts:
                lines.append(
                    f"- `/workspace/{ia['artifact_name']}` (from upstream `{ia['upstream_node_id']}`)"
                )
            lines.append("")
        if artifacts:
            lines.append(
                "When you produce a file or directory that downstream steps "
                "should receive, call "
                "`mcp__aviary_artifacts__save_as_artifact` with the artifact "
                "name and the `/workspace`-relative source path. Choose the "
                "right artifact per its description below. Call the tool "
                "once per artifact; do not save unrelated files."
            )
            lines.append("")
            lines.append("Declared artifacts:")
            for a in artifacts:
                desc = f" — {a['description']}" if a.get("description") else ""
                lines.append(f"- `{a['name']}`{desc}")
            lines.append("")
            lines.append(
                "**No verification after saving.** The \"Saved artifact\" "
                "tool result confirms the copy succeeded — do NOT run `ls`, "
                "`cat`, `wc`, `stat`, or any other check afterwards."
            )

    return (instruction or "").rstrip() + "\n" + "\n".join(lines)


def build_request_body(
    *,
    run_id: str,
    node_id: str,
    session_id: str,
    root_run_id: str,
    runtime_endpoint: str | None,
    rendered_prompt: str,
    data: dict,
    inputs: dict,
) -> tuple[dict, str, list[dict]]:
    """Assemble the supervisor ``/message`` request body.

    Returns (body, output_tool_cli_name, artifacts) so the caller can
    later pluck the structured result and produced-artifacts out of the
    assembled blocks without re-deriving names."""
    mcp_tool_ids = data.get("mcp_tool_ids") or []
    tools = [f"mcp__gateway__{t}" for t in mcp_tool_ids]

    output_tool = build_output_tool(data.get("structured_output_fields") or [])
    output_tool_cli_name = f"mcp__aviary_output__{output_tool['name']}"
    tools.append(output_tool_cli_name)

    artifacts = normalize_artifacts(data.get("artifacts") or [])
    if artifacts:
        tools.append(_ARTIFACT_TOOL_CLI_NAME)

    input_artifacts = collect_input_artifacts(inputs)
    full_instruction = augment_instruction(
        data.get("instruction") or "", output_tool, artifacts, input_artifacts,
    )

    body: dict = {
        "session_id": session_id,
        "content_parts": [{"text": rendered_prompt}],
        "agent_config": {
            "agent_id": f"wf:{run_id}:{node_id}",
            "runtime_endpoint": runtime_endpoint,
            "model_config": data.get("model_config") or {},
            "instruction": full_instruction,
            "tools": tools,
            "mcp_servers": {},
            "workflow_run": {
                "root_run_id": root_run_id,
                "node_id": node_id,
            },
            "artifacts": artifacts,
            "input_artifacts": input_artifacts,
            "max_turns": AGENT_STEP_MAX_TURNS,
        },
        "structured_outputs": [output_tool],
    }
    return body, output_tool_cli_name, artifacts


def extract_result(
    result: dict,
    *,
    output_tool_cli_name: str,
    artifacts: list[dict],
    root_run_id: str,
    node_id: str,
) -> dict:
    """Pull structured output + produced artifacts out of the assembled
    blocks, falling back to the last text block when the model skipped
    the final-response tool call."""
    blocks = result.get("assembled_blocks") or []
    captured = _tool_input(blocks, output_tool_cli_name)
    artifacts_produced = _artifacts_produced(blocks, artifacts, root_run_id, node_id)

    if isinstance(captured, dict) and captured:
        out = dict(captured)
        if not out.get("text"):
            # Model quirk: called the tool without `text`. Downstream
            # templates assume it's always present.
            out["text"] = _fallback_text(blocks)
        if artifacts_produced:
            out["artifacts_produced"] = artifacts_produced
        return out

    fallback: dict = {"text": _fallback_text(blocks)}
    if artifacts_produced:
        fallback["artifacts_produced"] = artifacts_produced
    return fallback


def _tool_input(blocks: list, cli_name: str) -> dict | None:
    for block in blocks:
        if block.get("type") == "tool_call" and block.get("name") == cli_name:
            payload = block.get("input")
            if isinstance(payload, dict):
                return payload
    return None


def _artifacts_produced(
    blocks: list, artifacts: list[dict], root_run_id: str, node_id: str,
) -> list[dict]:
    if not artifacts:
        return []
    declared = {a["name"] for a in artifacts}
    produced: dict[str, str] = {}
    for block in blocks:
        if block.get("type") != "tool_call" or block.get("name") != _ARTIFACT_TOOL_CLI_NAME:
            continue
        inp = block.get("input") or {}
        if not isinstance(inp, dict):
            continue
        name = inp.get("artifact_name")
        if not isinstance(name, str) or name not in declared:
            continue
        produced[name] = f"workflows/{root_run_id}/artifacts/{node_id}/{name}"
    return [{"name": n, "path": p} for n, p in produced.items()]


def _fallback_text(blocks: list) -> str:
    for block in reversed(blocks):
        if block.get("type") == "text":
            return block.get("content") or ""
    return ""

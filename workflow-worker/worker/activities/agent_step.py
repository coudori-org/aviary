"""Agent step activity — drives one supervisor `/message` round.

Each step runs inside a first-class ``sessions`` row so the frontend can
render history + live stream via the normal chat endpoints
(``GET /sessions/{id}`` + ``/api/sessions/{id}/ws``) — no workflow-specific
transcript plumbing required. The session is anchored to
``(workflow_run_id, node_id)`` and stays out of the chat sidebar via the
``workflow_run_id IS NULL`` filter in ``list_sessions_for_agent``.

Cancellation story:
  * Workflow sends the cancel signal.
  * Signal handler cancels the activity task; Temporal delivers the cancel
    to the running activity via the next heartbeat.
  * We capture `stream_id` from the supervisor's first `stream_started`
    event (same one the frontend uses to enable the abort button), then on
    CancelledError hit `/v1/streams/{stream_id}/abort`. Supervisor closes
    its outbound TCP to the runtime pod → `res.on("close")` fires → SDK
    aborts. Same path chat uses.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timezone

from jinja2 import Environment, StrictUndefined
from sqlalchemy import select
from temporalio import activity

from aviary_shared.db.models import Message, Session, WorkflowRun
from worker.db import session_scope
from worker.events import publish_session_event, subscribe_session
from worker.services import supervisor_client

logger = logging.getLogger(__name__)

_jinja = Environment(undefined=StrictUndefined, autoescape=False)

# How often the activity pokes Temporal so cancel requests get through.
# Tight interval because two activities sharing an event loop (parallel
# frontier dispatch) can temporarily starve each other while both are
# pumping SSE streams — the workflow-side `heartbeat_timeout` of 60s
# absorbs that gap, but we still want a fresh heartbeat roughly every
# few seconds to keep cancel latency low.
_HEARTBEAT_INTERVAL_SECONDS = 3.0

# Hard ceiling on assistant turns per step — protects against local-model
# verify loops (the model keeps inspecting its own output after it has
# already emitted the final response).
_AGENT_STEP_MAX_TURNS = 15


def step_session_id(run_id: str, node_id: str, root_run_id: str | None = None) -> str:
    """Deterministic per-(chain, node) session UUID.

    Anchored on the resume chain's **root** run so every run in the chain
    (fresh → resume → resume → …) resolves the same node to the same
    session — a resumed run can render its carried-over step's chat
    transcript instead of 404-ing on a session that only exists under the
    original run's id.

    Must be a valid UUID so the CLI accepts ``--session-id``; deriving via
    uuid5 also means the orchestrator can compute it without touching the
    DB (used to plumb the id into node_status events before the activity
    starts)."""
    anchor = root_run_id or run_id
    return str(uuid.uuid5(uuid.UUID(anchor), node_id))


async def _capture_stream_id(wf_session_id: str, stream_id_ref: dict) -> None:
    """Watch the supervisor's session channel just long enough to grab the
    ``stream_started`` event. The id is needed so cancel can abort the
    right outbound stream. Everything else on the channel is published by
    the supervisor — the frontend subscribes to it directly."""
    ps = await subscribe_session(wf_session_id)
    try:
        async for msg in ps.listen():
            if msg["type"] != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except json.JSONDecodeError:
                continue
            if event.get("type") == "stream_started":
                stream_id_ref["value"] = event.get("stream_id")
                return
    finally:
        with contextlib.suppress(Exception):
            await ps.unsubscribe()
            await ps.aclose()


@activity.defn
async def ensure_agent_step_session_activity(
    run_id: str, node_id: str, root_run_id: str | None = None,
) -> str:
    """Create (or find) the shared ``sessions`` row for this step and
    return its id. Called by the orchestrator *before* transitioning the
    node to ``running`` so the inspector's ChatTranscript can subscribe
    the moment the status event arrives — otherwise REST would 404 for
    the window between node_status publish and agent_step activity start.

    Anchors on ``root_run_id`` (the head of the resume chain) so a
    resumed run's re-executed step reuses the session row created by its
    ancestor run instead of writing a parallel row the original can't
    see. Session's workflow_run_id points at the root for the same
    reason — deleting a resumed run doesn't orphan the original's
    transcript.

    Owner is the workflow run's triggerer — same user whose JWT is
    forwarded to the supervisor, so the chat WS owner check passes for
    the inspector UI. Idempotent: resumed runs and activity retries both
    hit the same deterministic uuid5 and leave the existing row alone."""
    anchor_run_id = root_run_id or run_id
    session_id = step_session_id(run_id, node_id, root_run_id)
    session_uuid = uuid.UUID(session_id)
    anchor_uuid = uuid.UUID(anchor_run_id)
    current_uuid = uuid.UUID(run_id)
    async with session_scope() as db:
        existing = (await db.execute(
            select(Session).where(Session.id == session_uuid)
        )).scalar_one_or_none()
        if existing is not None:
            return session_id
        # Fall back to the current run for ``triggered_by`` if the anchor
        # row has been pruned — ownership stays consistent with whoever
        # is driving this execution.
        run = (await db.execute(
            select(WorkflowRun).where(WorkflowRun.id == current_uuid)
        )).scalar_one()
        db.add(Session(
            id=session_uuid,
            agent_id=None,
            created_by=run.triggered_by,
            title=f"{node_id}",
            workflow_run_id=anchor_uuid,
            node_id=node_id,
        ))
    return session_id


async def _save_user_message(session_id: str, content: str) -> None:
    """Persist the rendered prompt as the user turn and publish the
    ``user_message`` WS event so any live ChatTranscript renders the
    bubble without waiting for a history reload."""
    session_uuid = uuid.UUID(session_id)
    async with session_scope() as db:
        msg = Message(
            session_id=session_uuid,
            sender_type="user",
            sender_id=None,
            content=content,
            metadata_json={},
        )
        db.add(msg)
        session = (await db.execute(
            select(Session).where(Session.id == session_uuid)
        )).scalar_one()
        session.last_message_at = datetime.now(timezone.utc)
        await db.flush()
        message_id = str(msg.id)

    await publish_session_event(session_id, {
        "type": "user_message",
        "messageId": message_id,
        "sender_id": None,
        "content": content,
    })


async def _save_agent_message(
    session_id: str, content: str, blocks_meta: list[dict], *, terminal: str,
    error_message: str | None = None,
) -> None:
    """Persist the assistant turn in the chat-compatible shape so the
    normal REST history feed re-renders it after a reload, then publish
    the matching terminal event to ``session:{sid}:events`` so any live
    ChatTranscript subscribed to this session transitions out of the
    streaming state (mirrors what ``api`` does for chat sessions)."""
    meta: dict = {"blocks": blocks_meta} if blocks_meta else {}
    if terminal == "cancelled":
        meta["cancelled"] = True
    elif terminal == "error":
        meta["error"] = True

    fallback = (
        "[Cancelled]" if terminal == "cancelled"
        else (error_message or "[Error]") if terminal == "error"
        else ""
    )

    session_uuid = uuid.UUID(session_id)
    async with session_scope() as db:
        msg = Message(
            session_id=session_uuid,
            sender_type="agent",
            sender_id=None,
            content=content or fallback,
            metadata_json=meta,
        )
        db.add(msg)
        session = (await db.execute(
            select(Session).where(Session.id == session_uuid)
        )).scalar_one()
        session.last_message_at = datetime.now(timezone.utc)
        await db.flush()
        message_id = str(msg.id)

    event: dict = {"type": terminal, "messageId": message_id}
    if terminal == "error" and error_message:
        event["message"] = error_message
    await publish_session_event(session_id, event)


@activity.defn
async def run_agent_step_activity(
    run_id: str,
    node_id: str,
    owner_external_id: str,
    user_token: str | None,
    data: dict,
    trigger_data: dict,
    inputs: dict,
    input_value,
    runtime_endpoint: str | None = None,
    root_run_id: str | None = None,
) -> dict:
    # Each step gets its own session so runtime isolation works per-node and
    # independent branches run in parallel. Anchor on root_run_id so the
    # session id stays stable across the resume chain.
    effective_root = root_run_id or run_id
    session_id = step_session_id(run_id, node_id, root_run_id)

    prompt_tpl = data.get("prompt_template") or ""
    rendered_prompt = _jinja.from_string(prompt_tpl).render(
        input=input_value, inputs=inputs, trigger=trigger_data,
    )

    # Row was created ahead of time by the orchestrator via
    # ensure_agent_step_session_activity; persist the user turn into it.
    await _save_user_message(session_id, rendered_prompt)

    mcp_tool_ids = data.get("mcp_tool_ids") or []
    tools = [f"mcp__gateway__{t}" for t in mcp_tool_ids]

    # Every agent_step outputs a structured dict so downstream templates can
    # reference named fields uniformly. `text` is always present and holds
    # the user-facing answer; users can add extra fields in the inspector.
    # The user may also supply a description for the `text` entry itself via
    # a leading {name: "text", ...} row in `structured_output_fields`.
    output_tool = _build_output_tool(data.get("structured_output_fields") or [])
    output_tool_cli_name = f"mcp__aviary_output__{output_tool['name']}"
    tools.append(output_tool_cli_name)

    artifacts = _normalize_artifacts(data.get("artifacts") or [])
    if artifacts:
        tools.append("mcp__aviary_artifacts__save_as_artifact")

    input_artifacts = _collect_input_artifacts(inputs)

    instruction = data.get("instruction") or ""
    instruction = _augment_instruction_with_output_tool(instruction, output_tool)
    instruction = _augment_instruction_with_artifacts(instruction, artifacts, input_artifacts)

    body: dict = {
        "session_id": session_id,
        "content_parts": [{"text": rendered_prompt}],
        "agent_config": {
            "agent_id": f"wf:{run_id}:{node_id}",
            "runtime_endpoint": runtime_endpoint,
            "model_config": data.get("model_config") or {},
            "instruction": instruction,
            "tools": tools,
            "mcp_servers": {},
            "workflow_run": {
                "root_run_id": effective_root,
                "node_id": node_id,
            },
            "artifacts": artifacts,
            "input_artifacts": input_artifacts,
            # Hard safety net against verify-loop behaviour on weak local
            # models. A sane single-step agent never needs this many turns;
            # if yours does, split it into smaller workflow nodes.
            "max_turns": _AGENT_STEP_MAX_TURNS,
        },
        "structured_outputs": [output_tool],
    }
    if user_token is None:
        body["on_behalf_of_sub"] = owner_external_id

    stream_id_ref: dict = {"value": None}
    capture_task = asyncio.create_task(_capture_stream_id(session_id, stream_id_ref))
    supervisor_task = asyncio.create_task(
        supervisor_client.post_message(session_id, body, user_token=user_token)
    )

    # First heartbeat up front — ensures a fresh timestamp before the loop
    # even runs its first iteration, in case event-loop scheduling delays
    # the first heartbeat under concurrent parallel dispatch.
    activity.heartbeat()

    try:
        # Heartbeat-pump until supervisor returns. shield() keeps the
        # supervisor task alive even when wait_for times out.
        while not supervisor_task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(supervisor_task),
                    timeout=_HEARTBEAT_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                activity.heartbeat()
                continue
        result = supervisor_task.result()
    except asyncio.CancelledError:
        sid = stream_id_ref.get("value")
        if sid:
            logger.info("agent_step cancelled; aborting supervisor stream=%s", sid)
            await supervisor_client.abort_stream(sid, user_token=user_token)
        # abort_stream closes the outbound TCP, which the supervisor's
        # `/message` call translates into a normal return with
        # status=aborted + assembled partial — await it so the partial
        # lands in the transcript instead of vanishing.
        partial: dict | None = None
        with contextlib.suppress(Exception):
            partial = await supervisor_task
        if partial is not None:
            await _save_agent_message(
                session_id,
                partial.get("assembled_text", ""),
                partial.get("assembled_blocks", []),
                terminal="cancelled",
            )
        raise
    finally:
        capture_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await capture_task

    status = result.get("status")
    if status == "error":
        err_msg = result.get("message") or "agent step failed"
        await _save_agent_message(
            session_id,
            result.get("assembled_text", ""),
            result.get("assembled_blocks", []),
            terminal="error",
            error_message=err_msg,
        )
        raise RuntimeError(err_msg)
    if status == "aborted":
        await _save_agent_message(
            session_id,
            result.get("assembled_text", ""),
            result.get("assembled_blocks", []),
            terminal="cancelled",
        )
    else:
        await _save_agent_message(
            session_id,
            result.get("assembled_text", ""),
            result.get("assembled_blocks", []),
            terminal="done",
        )

    captured = _extract_tool_input(result.get("assembled_blocks") or [], output_tool_cli_name)
    artifacts_produced = _extract_artifacts_produced(
        result.get("assembled_blocks") or [], artifacts, effective_root, node_id,
    )
    if isinstance(captured, dict) and captured:
        # Guarantee `text` even when a model-quirk omits it — downstream
        # templates assume it's always there. Fall back to assembled text.
        if not captured.get("text"):
            captured = {**captured, "text": _fallback_text(result)}
        if artifacts_produced:
            captured = {**captured, "artifacts_produced": artifacts_produced}
        return captured
    # Model didn't call the final-response tool (e.g. hit a hard error mid-
    # stream). Fall back to the last text block so the node still produces
    # a usable `text` output.
    fallback: dict = {"text": _fallback_text(result)}
    if artifacts_produced:
        fallback["artifacts_produced"] = artifacts_produced
    return fallback


def _extract_tool_input(blocks: list, cli_name: str) -> dict | None:
    for block in blocks:
        if block.get("type") == "tool_call" and block.get("name") == cli_name:
            payload = block.get("input")
            if isinstance(payload, dict):
                return payload
    return None


_ARTIFACT_TOOL_CLI_NAME = "mcp__aviary_artifacts__save_as_artifact"


def _extract_artifacts_produced(
    blocks: list, artifacts: list[dict], root_run_id: str, node_id: str,
) -> list[dict]:
    """Walk the assembled blocks for every successful save_as_artifact call
    and emit a canonical {name, path} entry for downstream nodes."""
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


def _fallback_text(result: dict) -> str:
    for block in reversed(result.get("assembled_blocks") or []):
        if block.get("type") == "text":
            return block.get("content") or ""
    return ""


_ALLOWED_FIELD_TYPES = {"str", "list"}
_DEFAULT_TEXT_DESCRIPTION = "The final user-facing response text for this step — a concise summary of the agent's answer."
_OUTPUT_TOOL_NAME = "emit_final_response"
_OUTPUT_TOOL_DESCRIPTION = "Emit the final structured response for this workflow step. Call this exactly once, as your last action, with every field populated."


def _build_output_tool(raw: list) -> dict:
    """Normalise `structured_output_fields` into a structured_outputs[] entry.

    A single `text` entry anywhere in `raw` is treated as a description
    override (name and type are locked). All other entries — after name /
    type / duplicate validation — become extras appended in order.
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


def _normalize_artifacts(raw: list) -> list[dict]:
    """Filter declared artifacts down to well-formed {name, description}
    entries; duplicates keep the first occurrence."""
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


def _collect_input_artifacts(inputs: dict) -> list[dict]:
    """Pull upstream `artifacts_produced` from the context dict into a flat
    list of {upstream_node_id, artifact_name}. Used by the runtime to
    pre-copy files into the step's `/workspace` before the SDK starts."""
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


def _augment_instruction_with_output_tool(instruction: str, tool: dict) -> str:
    """Append a short guidance block so the model consistently calls the
    dynamically-registered output tool. The runtime no longer injects any
    system-prompt suffix of its own — callers own the prompt fully."""
    lines = ["", "## Final response"]
    lines.append(
        f"Emit your final answer by calling the "
        f"`mcp__aviary_output__{tool['name']}` tool exactly once, at the very "
        f"end of your work. The tool call IS the response — do not also write "
        f"it as plain text."
    )
    lines.append("")
    lines.append("Fields:")
    for f in tool["fields"]:
        t = "array of strings" if f["type"] == "list" else "string"
        desc = f" — {f['description']}" if f.get("description") else ""
        lines.append(f"- `{f['name']}` ({t}){desc}")
    lines.append("")
    lines.append(
        "**Stop rule (important):** Immediately after the "
        f"`mcp__aviary_output__{tool['name']}` tool call completes, END YOUR "
        "TURN. Do not run any more tools, do not re-read or re-verify files, "
        "do not list directories, do not add a closing message. The tool "
        "result text (\"recorded.\") is just an acknowledgement; it is NOT a "
        "request for further action."
    )
    return (instruction or "").rstrip() + "\n" + "\n".join(lines)


def _augment_instruction_with_artifacts(
    instruction: str, artifacts: list[dict], input_artifacts: list[dict],
) -> str:
    """Document the artifacts contract: which named artifacts this step is
    expected to produce (`save_as_artifact`) and which upstream artifacts
    were pre-copied into `/workspace/{name}/`."""
    if not artifacts and not input_artifacts:
        return instruction
    lines: list[str] = ["", "## Artifacts"]
    if input_artifacts:
        lines.append("Upstream artifacts have been copied into your working directory:")
        for ia in input_artifacts:
            lines.append(
                f"- `/workspace/{ia['artifact_name']}` (from upstream `{ia['upstream_node_id']}`)"
            )
        lines.append("")
    if artifacts:
        lines.append(
            "When you produce a file or directory that downstream steps should "
            "receive, call `mcp__aviary_artifacts__save_as_artifact` with the "
            "artifact name and the `/workspace`-relative source path. Choose "
            "the right artifact per its description below. Call the tool once "
            "per artifact; do not save unrelated files."
        )
        lines.append("")
        lines.append("Declared artifacts:")
        for a in artifacts:
            desc = f" — {a['description']}" if a.get("description") else ""
            lines.append(f"- `{a['name']}`{desc}")
        lines.append("")
        lines.append(
            "**No verification after saving.** The \"Saved artifact\" tool "
            "result confirms the copy succeeded — do NOT run `ls`, `cat`, "
            "`wc`, `stat`, or any other check on the file afterwards. Move "
            "straight to the final response tool call."
        )
    return (instruction or "").rstrip() + "\n" + "\n".join(lines)

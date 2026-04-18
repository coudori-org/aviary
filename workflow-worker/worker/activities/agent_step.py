"""Agent step activity — drives one supervisor `/message` round.

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

from jinja2 import Environment, StrictUndefined
from temporalio import activity

from worker.events import publish_event, subscribe_session
from worker.services import supervisor_client

logger = logging.getLogger(__name__)

_jinja = Environment(undefined=StrictUndefined, autoescape=False)

_LOG_EVENT_TYPES = {"chunk", "thinking", "tool_use", "tool_result"}

# How often the activity pokes Temporal so cancel requests get through.
_HEARTBEAT_INTERVAL_SECONDS = 5.0


async def _fan_in(
    run_id: str, node_id: str, wf_session_id: str, stream_id_ref: dict
) -> None:
    """Rewrite supervisor session events as node_log on the workflow
    channel. Captures the stream_id from `stream_started` so cancel can
    abort it later."""
    ps = await subscribe_session(wf_session_id)
    try:
        async for msg in ps.listen():
            if msg["type"] != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except json.JSONDecodeError:
                continue
            etype = event.get("type")
            if etype == "stream_started":
                stream_id_ref["value"] = event.get("stream_id")
                continue
            if etype not in _LOG_EVENT_TYPES:
                continue

            log: dict = {"type": "node_log", "node_id": node_id, "log_type": etype}
            if etype in ("chunk", "thinking"):
                log["content"] = event.get("content", "")
            elif etype == "tool_use":
                log["name"] = event.get("name")
                log["input"] = event.get("input")
                log["tool_use_id"] = event.get("tool_use_id")
            elif etype == "tool_result":
                log["content"] = event.get("content")
                log["tool_use_id"] = event.get("tool_use_id")
                log["is_error"] = event.get("is_error", False)
            await publish_event(run_id, log)
    finally:
        with contextlib.suppress(Exception):
            await ps.unsubscribe()
            await ps.aclose()


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
) -> dict:
    # Claude CLI requires session_id to be a valid UUID. run_id already is
    # one, so reuse it directly — the workflow run and its sole Claude
    # session share a namespace.
    wf_session_id = run_id

    prompt_tpl = data.get("prompt_template") or ""
    rendered_prompt = _jinja.from_string(prompt_tpl).render(
        input=input_value, inputs=inputs, trigger=trigger_data,
    )

    mcp_tool_ids = data.get("mcp_tool_ids") or []
    tools = [f"mcp__gateway__{t}" for t in mcp_tool_ids]

    body: dict = {
        "session_id": wf_session_id,
        "content_parts": [{"text": rendered_prompt}],
        "agent_config": {
            "agent_id": f"wf:{run_id}:{node_id}",
            "runtime_endpoint": runtime_endpoint,
            "model_config": data.get("model_config") or {},
            "instruction": data.get("instruction") or "",
            "tools": tools,
            "mcp_servers": {},
        },
    }
    if user_token is None:
        body["on_behalf_of_sub"] = owner_external_id

    stream_id_ref: dict = {"value": None}
    fan_in_task = asyncio.create_task(_fan_in(run_id, node_id, wf_session_id, stream_id_ref))
    supervisor_task = asyncio.create_task(
        supervisor_client.post_message(wf_session_id, body, user_token=user_token)
    )

    try:
        # Heartbeat-pump until supervisor returns. shield() keeps the
        # supervisor task alive even when wait_for times out.
        while not supervisor_task.done():
            activity.heartbeat()
            try:
                await asyncio.wait_for(
                    asyncio.shield(supervisor_task),
                    timeout=_HEARTBEAT_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue
        result = supervisor_task.result()
    except asyncio.CancelledError:
        sid = stream_id_ref.get("value")
        if sid:
            logger.info("agent_step cancelled; aborting supervisor stream=%s", sid)
            await supervisor_client.abort_stream(sid, user_token=user_token)
        supervisor_task.cancel()
        with contextlib.suppress(Exception):
            await supervisor_task
        raise
    finally:
        fan_in_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await fan_in_task

    if result.get("status") == "error":
        raise RuntimeError(result.get("message") or "agent step failed")

    text = ""
    for block in reversed(result.get("assembled_blocks") or []):
        if block.get("type") == "text":
            text = block.get("content") or ""
            break
    return {"text": text}

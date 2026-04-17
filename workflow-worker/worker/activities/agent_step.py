"""Agent step activity — drives one supervisor `/message` round.

Two things happen in parallel inside this activity:
  1. A background task subscribes to the supervisor's session channel
     (`session:{wf:{run}}:events`) and republishes each chunk / thinking /
     tool_use / tool_result event as a `node_log` on the workflow run
     channel so the UI sees live LLM output under the right node.
  2. A blocking HTTP POST to supervisor waits for the assembled response.

The supervisor keeps writing to Redis regardless of who's listening, so
the fan-in task is purely for surfacing live logs to the workflow WS —
the final output always comes back via the HTTP response.
"""

from __future__ import annotations

import asyncio
import json
import logging

from jinja2 import Environment, StrictUndefined
from temporalio import activity

from worker.events import publish_event, subscribe_session
from worker.services import supervisor_client

logger = logging.getLogger(__name__)

_jinja = Environment(undefined=StrictUndefined, autoescape=False)

# Supervisor event types we care about for per-node logs.
_LOG_EVENT_TYPES = {"chunk", "thinking", "tool_use", "tool_result"}


async def _fan_in(run_id: str, node_id: str, wf_session_id: str) -> None:
    """Rewrite supervisor session events as node_log events on the workflow
    channel. Cancelled by the caller once the HTTP response lands."""
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
        try:
            await ps.unsubscribe()
            await ps.aclose()
        except Exception:  # noqa: BLE001
            pass


@activity.defn
async def run_agent_step_activity(
    run_id: str,
    node_id: str,
    owner_external_id: str,
    user_token: str | None,
    data: dict,
    trigger_data: dict,
    inputs: dict,
) -> dict:
    """Render prompt, call supervisor, relay live events, return assembly."""
    wf_session_id = f"wf:{run_id}"

    prompt_tpl = data.get("prompt_template") or ""
    rendered_prompt = _jinja.from_string(prompt_tpl).render(
        inputs=inputs, trigger=trigger_data
    )

    body: dict = {
        "session_id": wf_session_id,
        "content_parts": [{"text": rendered_prompt}],
        "agent_config": {
            "agent_id": f"wf:{run_id}:{node_id}",
            "runtime_endpoint": None,
            "model_config": data.get("model_config") or {},
            "instruction": data.get("instruction") or "",
            "tools": [],
            "mcp_servers": {},
        },
    }
    # Worker-auth fallback only when there's no live user JWT to forward.
    if user_token is None:
        body["on_behalf_of_sub"] = owner_external_id

    fan_in_task = asyncio.create_task(_fan_in(run_id, node_id, wf_session_id))
    try:
        result = await supervisor_client.post_message(
            wf_session_id, body, user_token=user_token,
        )
    finally:
        fan_in_task.cancel()
        try:
            await fan_in_task
        except asyncio.CancelledError:
            pass

    if result.get("status") == "error":
        raise RuntimeError(result.get("message") or "agent step failed")

    return {
        "assembled_text": result.get("assembled_text"),
        "assembled_blocks": result.get("assembled_blocks") or [],
        "stream_id": result.get("stream_id"),
    }

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from temporalio import activity

from aviary_shared.db.models import Message, Session, WorkflowRun
from worker.db import session_scope
from worker.events import publisher, subscribe_session
from worker.services import supervisor_client

from .agent_step_helpers import (
    build_request_body,
    extract_result,
    render_prompt,
    step_session_id,
)

logger = logging.getLogger(__name__)

# Tight heartbeat so cancel latency stays low even under SSE-pumping starvation.
_HEARTBEAT_INTERVAL_SECONDS = 3.0


async def _capture_stream_id(session_id: str, stream_id_ref: dict) -> None:
    ps = await subscribe_session(session_id)
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
    # Anchor on root_run_id so resumed runs reuse the ancestor's session row.
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
        await db.execute(
            update(Session)
            .where(Session.id == session_uuid)
            .values(last_message_at=datetime.now(timezone.utc))
        )
        await db.flush()
        message_id = str(msg.id)

    await publisher.session_user_message(
        session_id, message_id=message_id, sender_id=None, content=content,
    )


async def _save_agent_message(
    session_id: str, result: dict, *, terminal: str, error_message: str | None = None,
) -> None:
    content = result.get("assembled_text", "") if isinstance(result, dict) else ""
    blocks = result.get("assembled_blocks", []) if isinstance(result, dict) else []

    meta: dict = {"blocks": blocks} if blocks else {}
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
        await db.execute(
            update(Session)
            .where(Session.id == session_uuid)
            .values(last_message_at=datetime.now(timezone.utc))
        )
        await db.flush()
        message_id = str(msg.id)

    await publisher.session_terminal(
        session_id, message_id=message_id, status=terminal, error=error_message,
    )


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
    effective_root = root_run_id or run_id
    session_id = step_session_id(run_id, node_id, root_run_id)

    rendered_prompt = render_prompt(
        data.get("prompt_template") or "",
        input_value=input_value, inputs=inputs, trigger_data=trigger_data,
    )
    await _save_user_message(session_id, rendered_prompt)

    body, output_tool_cli_name, artifacts = build_request_body(
        run_id=run_id, node_id=node_id, session_id=session_id,
        root_run_id=effective_root, runtime_endpoint=runtime_endpoint,
        rendered_prompt=rendered_prompt, data=data, inputs=inputs,
    )
    if user_token is None:
        body["on_behalf_of_sub"] = owner_external_id

    stream_id_ref: dict = {"value": None}
    capture_task = asyncio.create_task(_capture_stream_id(session_id, stream_id_ref))
    supervisor_task = asyncio.create_task(
        supervisor_client.post_message(session_id, body, user_token=user_token)
    )

    # Fresh heartbeat before the loop so event-loop scheduling can't delay
    # the first tick past `heartbeat_timeout` under parallel dispatch.
    activity.heartbeat()

    try:
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
        # abort_stream closes outbound TCP; supervisor returns status=aborted
        # with whatever partial was assembled. Await it so the partial lands
        # in the transcript instead of vanishing.
        partial: dict | None = None
        with contextlib.suppress(Exception):
            partial = await supervisor_task
        if partial is not None:
            await _save_agent_message(session_id, partial, terminal="cancelled")
        raise
    finally:
        capture_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await capture_task

    status = result.get("status")
    if status == "error":
        err_msg = result.get("message") or "agent step failed"
        await _save_agent_message(
            session_id, result, terminal="error", error_message=err_msg,
        )
        raise RuntimeError(err_msg)

    terminal = "cancelled" if status == "aborted" else "done"
    await _save_agent_message(session_id, result, terminal=terminal)

    return extract_result(
        result,
        output_tool_cli_name=output_tool_cli_name,
        artifacts=artifacts,
        root_run_id=effective_root,
        node_id=node_id,
    )

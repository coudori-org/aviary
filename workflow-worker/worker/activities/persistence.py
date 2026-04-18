"""DB-writing activities.

Each status transition writes to Postgres and broadcasts the same event to
Redis in the same activity — persistence and fan-out succeed or fail
together so a live WS listener never observes a state the DB doesn't
agree with.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from temporalio import activity

from aviary_shared.db.models import WorkflowNodeRun, WorkflowRun
from worker.db import session_scope
from worker.events import publish_event

logger = logging.getLogger(__name__)

_TERMINAL_NODE_STATUSES = {"completed", "failed", "skipped"}


@activity.defn
async def set_run_status(run_id: str, status: str, error: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    values: dict = {"status": status}
    if error is not None:
        values["error"] = error
    if status == "running":
        values["started_at"] = now
    elif status in ("completed", "failed", "cancelled"):
        values["completed_at"] = now

    async with session_scope() as session:
        await session.execute(
            update(WorkflowRun).where(WorkflowRun.id == uuid.UUID(run_id)).values(**values)
        )

    event: dict = {"type": "run_status", "status": status}
    if error:
        event["error"] = error
    await publish_event(run_id, event)
    logger.info("run=%s status=%s", run_id, status)


@activity.defn
async def set_node_status(
    run_id: str,
    node_id: str,
    node_type: str,
    status: str,
    input_data: dict | None = None,
    output_data: dict | None = None,
    error: str | None = None,
    session_id: str | None = None,
) -> None:
    """Upsert the WorkflowNodeRun row, then publish the matching event.

    Arguments with `None` mean "don't overwrite" except for status, which
    always applies. Passing `input_data` on the "running" transition and
    `output_data` on "completed" gives listeners the full story.
    ``session_id`` (agent_step only) is tunneled on the event so the
    inspector's ChatTranscript has a sessionId to subscribe to the moment
    the step transitions to running.
    """
    now = datetime.now(timezone.utc)
    run_uuid = uuid.UUID(run_id)

    async with session_scope() as session:
        nr = (
            await session.execute(
                select(WorkflowNodeRun).where(
                    WorkflowNodeRun.run_id == run_uuid,
                    WorkflowNodeRun.node_id == node_id,
                )
            )
        ).scalar_one_or_none()

        if nr is None:
            nr = WorkflowNodeRun(
                run_id=run_uuid,
                node_id=node_id,
                node_type=node_type,
                status=status,
                input_data=input_data,
                output_data=output_data,
                error=error,
                started_at=now if status == "running" else None,
                completed_at=now if status in _TERMINAL_NODE_STATUSES else None,
            )
            session.add(nr)
        else:
            nr.status = status
            if input_data is not None:
                nr.input_data = input_data
            if output_data is not None:
                nr.output_data = output_data
            if error is not None:
                nr.error = error
            if status == "running" and nr.started_at is None:
                nr.started_at = now
            if status in _TERMINAL_NODE_STATUSES and nr.completed_at is None:
                nr.completed_at = now

    event: dict = {
        "type": "node_status",
        "node_id": node_id,
        "node_type": node_type,
        "status": status,
    }
    if input_data is not None:
        event["input_data"] = input_data
    if output_data is not None:
        event["output_data"] = output_data
    if error:
        event["error"] = error
    if session_id:
        event["session_id"] = session_id
    await publish_event(run_id, event)
    logger.info("run=%s node=%s status=%s", run_id, node_id, status)

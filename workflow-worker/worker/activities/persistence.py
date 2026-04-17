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

from sqlalchemy import update
from temporalio import activity

from aviary_shared.db.models import WorkflowRun
from worker.db import session_scope
from worker.events import publish_event

logger = logging.getLogger(__name__)


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

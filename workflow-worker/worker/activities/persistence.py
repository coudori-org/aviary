"""DB-writing activities.

Activities are the only place side effects happen. The workflow is
deterministic — it decides which activity to run, with what inputs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import update
from temporalio import activity

from aviary_shared.db.models import WorkflowRun
from worker.db import session_scope

logger = logging.getLogger(__name__)


@activity.defn
async def set_run_status(run_id: str, status: str, error: str | None = None) -> None:
    """Transition a WorkflowRun row to `status` and stamp timestamps."""
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
    logger.info("run=%s status=%s", run_id, status)

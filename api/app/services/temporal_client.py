"""Thin wrapper over temporalio.client.Client.

Single process-wide connection created at FastAPI startup. Callers use
`start_workflow_run` / `cancel_workflow_run` instead of touching the
client directly, so request handlers stay free of Temporal specifics.
"""

from __future__ import annotations

import logging

from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from app.config import settings
from aviary_shared.workflow_types import WorkflowRunInput

logger = logging.getLogger(__name__)

_client: Client | None = None


async def init_client() -> None:
    global _client
    _client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace
    )
    logger.info(
        "Temporal client connected host=%s namespace=%s",
        settings.temporal_host, settings.temporal_namespace,
    )


async def close_client() -> None:
    # temporalio.Client has no explicit close; gRPC channels close on process exit.
    return


def get_client() -> Client:
    if _client is None:
        raise RuntimeError("Temporal client not initialized")
    return _client


async def start_workflow_run(inp: WorkflowRunInput) -> str:
    """Start a WorkflowRun. Returns Temporal's internal run_id."""
    handle = await get_client().start_workflow(
        "WorkflowRun",
        inp,
        id=inp.run_id,
        task_queue=settings.temporal_task_queue,
    )
    return handle.result_run_id


async def cancel_workflow_run(run_id: str) -> None:
    """Send a cooperative `cancel` signal. The worker's signal handler flips
    an internal flag AND cancels the in-flight activity task, so an
    agent_step mid-stream gets its supervisor abort call on the way out.

    Idempotent: signalling a workflow that already finished is a no-op
    instead of an error.
    """
    handle = get_client().get_workflow_handle(run_id)
    try:
        await handle.signal("cancel")
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            logger.info("cancel skipped — workflow %s already finished", run_id)
            return
        raise

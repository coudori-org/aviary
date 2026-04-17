"""Worker entrypoint. Connects to Temporal and polls the aviary-workflows
task queue. Shutdown is handled by Temporal's SIGTERM/SIGINT integration."""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from worker.activities.persistence import set_run_status
from worker.config import settings
from worker.workflows.workflow_run import WorkflowRunWorkflow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("workflow-worker")


async def main() -> None:
    logger.info(
        "Connecting to Temporal host=%s namespace=%s",
        settings.temporal_host, settings.temporal_namespace,
    )
    client = await Client.connect(
        settings.temporal_host, namespace=settings.temporal_namespace
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[WorkflowRunWorkflow],
        activities=[set_run_status],
    )
    logger.info("Worker ready on task_queue=%s", settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

"""Top-level workflow definition.

Phase 5 skeleton: accepts a run and flips its status through
running → (cancelled|completed). Phase 8 adds topological DAG traversal
and per-node activity dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from worker.activities.persistence import set_run_status


@dataclass
class WorkflowRunInput:
    run_id: str                   # WorkflowRun.id (also = Temporal workflow_id)
    owner_external_id: str        # OIDC sub — used by supervisor worker-auth path
    definition_snapshot: dict     # React Flow graph to execute
    trigger_data: dict


@dataclass
class WorkflowRunResult:
    status: str   # "completed" | "cancelled" | "failed"


@workflow.defn(name="WorkflowRun")
class WorkflowRunWorkflow:
    def __init__(self) -> None:
        self._cancelled = False

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    @workflow.run
    async def run(self, inp: WorkflowRunInput) -> WorkflowRunResult:
        await workflow.execute_activity(
            set_run_status,
            args=[inp.run_id, "running", None],
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Phase 5: no DAG execution yet — phases 8/9 add per-node activities.
        final = "cancelled" if self._cancelled else "completed"

        await workflow.execute_activity(
            set_run_status,
            args=[inp.run_id, final, None],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return WorkflowRunResult(status=final)

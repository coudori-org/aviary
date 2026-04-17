"""WorkflowRun — top-level orchestration.

Executes nodes in topological order, threading each node's output into a
shared context so downstream nodes can reference upstream payloads. A
failed condition propagates `skipped` to its descendants. A cancel signal
aborts the in-flight node (agent steps abort their supervisor stream on
the way out) and marks every later node as skipped.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from aviary_shared.workflow_types import WorkflowRunInput, WorkflowRunResult
    from worker.activities.agent_step import run_agent_step_activity
    from worker.activities.nodes import (
        evaluate_condition_activity,
        merge_activity,
        parse_payload_activity,
        render_template_activity,
    )
    from worker.activities.persistence import set_node_status, set_run_status
    from worker.dag import PlanNode, build_topological_plan, downstream_of, upstream_of


_ACT_TIMEOUT = timedelta(seconds=30)
_AGENT_STEP_TIMEOUT = timedelta(minutes=30)  # LLM turns can run long
_TRIGGER_TYPES = {"manual_trigger", "webhook_trigger"}


async def _dispatch_node(node: PlanNode, inputs: dict, inp: WorkflowRunInput) -> dict:
    """Map a node type to the activity that owns its side effects."""
    if node.type in _TRIGGER_TYPES:
        return {"payload": inp.trigger_data}
    ctx = {"inputs": inputs, "trigger": inp.trigger_data}
    if node.type == "template":
        return await workflow.execute_activity(
            render_template_activity,
            args=[node.data.get("template", ""), ctx],
            start_to_close_timeout=_ACT_TIMEOUT,
        )
    if node.type == "condition":
        return await workflow.execute_activity(
            evaluate_condition_activity,
            args=[node.data.get("expression", ""), ctx],
            start_to_close_timeout=_ACT_TIMEOUT,
        )
    if node.type == "payload_parser":
        source = next(iter(inputs.values())) if inputs else inp.trigger_data
        return await workflow.execute_activity(
            parse_payload_activity,
            args=[node.data.get("mapping", {}), source],
            start_to_close_timeout=_ACT_TIMEOUT,
        )
    if node.type == "merge":
        return await workflow.execute_activity(
            merge_activity, args=[inputs],
            start_to_close_timeout=_ACT_TIMEOUT,
        )
    if node.type == "agent_step":
        # LLM calls are non-deterministic — a failure usually means the model
        # refused, an API key was missing, or the backend returned an error.
        # Blindly retrying doubles cost without fixing anything, so we cap at
        # one attempt and let the workflow fail fast.
        #
        # `heartbeat_timeout` is what makes cancel actually reach the
        # activity process — without it, Temporal has no path to deliver
        # the cancel until the activity returns.
        return await workflow.execute_activity(
            run_agent_step_activity,
            args=[
                inp.run_id, node.id, inp.owner_external_id, inp.user_token,
                node.data, inp.trigger_data, inputs,
            ],
            start_to_close_timeout=_AGENT_STEP_TIMEOUT,
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
    raise ValueError(f"Unknown node type: {node.type}")


@workflow.defn(name="WorkflowRun")
class WorkflowRunWorkflow:
    def __init__(self) -> None:
        self._cancelled = False
        self._current_task: asyncio.Task | None = None

    @workflow.signal
    def cancel(self) -> None:
        """Set the cancel flag AND cancel the in-flight node task. The
        task's coroutine is what Temporal uses to signal the running
        activity, so cancelling it here is what actually aborts a
        long-running agent_step mid-stream."""
        self._cancelled = True
        current = self._current_task
        if current is not None and not current.done():
            current.cancel()

    @workflow.run
    async def run(self, inp: WorkflowRunInput) -> WorkflowRunResult:
        await workflow.execute_activity(
            set_run_status, args=[inp.run_id, "running", None],
            start_to_close_timeout=_ACT_TIMEOUT,
        )

        try:
            plan = build_topological_plan(inp.definition_snapshot)
        except ValueError as e:
            await workflow.execute_activity(
                set_run_status, args=[inp.run_id, "failed", str(e)],
                start_to_close_timeout=_ACT_TIMEOUT,
            )
            return WorkflowRunResult(status="failed")

        edges = inp.definition_snapshot.get("edges", [])
        context: dict = {}
        skipped: set[str] = set()

        for node in plan:
            should_skip = self._cancelled or node.id in skipped
            if should_skip:
                await workflow.execute_activity(
                    set_node_status,
                    args=[inp.run_id, node.id, node.type, "skipped", None, None, None],
                    start_to_close_timeout=_ACT_TIMEOUT,
                )
                continue

            inputs = {src: context.get(src) for src in upstream_of(node.id, edges)}
            await workflow.execute_activity(
                set_node_status,
                args=[inp.run_id, node.id, node.type, "running", inputs, None, None],
                start_to_close_timeout=_ACT_TIMEOUT,
            )

            self._current_task = asyncio.ensure_future(_dispatch_node(node, inputs, inp))
            try:
                output = await self._current_task
            except asyncio.CancelledError:
                # Activity was cancelled mid-flight (agent_step aborted its
                # supervisor stream on the way out).
                await workflow.execute_activity(
                    set_node_status,
                    args=[inp.run_id, node.id, node.type, "skipped", None, None, None],
                    start_to_close_timeout=_ACT_TIMEOUT,
                )
                continue
            except ActivityError as e:
                # Temporal wraps the real exception — unwrap so the UI sees
                # "Claude Code process exited with code 1" rather than the
                # generic "Activity task failed".
                err = str(e.cause) if e.cause else str(e)
                await workflow.execute_activity(
                    set_node_status,
                    args=[inp.run_id, node.id, node.type, "failed", None, None, err],
                    start_to_close_timeout=_ACT_TIMEOUT,
                )
                await workflow.execute_activity(
                    set_run_status, args=[inp.run_id, "failed", err],
                    start_to_close_timeout=_ACT_TIMEOUT,
                )
                return WorkflowRunResult(status="failed")
            finally:
                self._current_task = None

            context[node.id] = output
            await workflow.execute_activity(
                set_node_status,
                args=[inp.run_id, node.id, node.type, "completed", None, output, None],
                start_to_close_timeout=_ACT_TIMEOUT,
            )

            if node.type == "condition" and not output.get("result"):
                for ds in downstream_of(node.id, edges):
                    skipped.add(ds)

        final = "cancelled" if self._cancelled else "completed"
        await workflow.execute_activity(
            set_run_status, args=[inp.run_id, final, None],
            start_to_close_timeout=_ACT_TIMEOUT,
        )
        return WorkflowRunResult(status=final)

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
from temporalio.exceptions import ActivityError, CancelledError as TemporalCancelledError

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

# Default for every activity — fail fast on the first error. Node
# activities can opt into retry via `node.data.retry_count` set in the
# builder's Inspector. Persistence/publish activities stay at 1 attempt
# because the run's own status machine handles surfacing the failure.
_DEFAULT_RETRY = RetryPolicy(maximum_attempts=1)
_MAX_RETRY = 10


def _node_retry(node_data: dict) -> RetryPolicy:
    raw = node_data.get("retry_count")
    try:
        attempts = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        attempts = 1
    attempts = max(1, min(attempts, _MAX_RETRY))
    return RetryPolicy(maximum_attempts=attempts)


def _single_input(inputs: dict, trigger_data: dict):
    """Collapse `inputs` into a single `input` value for templates.

    - 0 upstream edges → trigger payload (lets `{{ input.text }}` work
      even for a node wired directly from a trigger).
    - 1 upstream edge → that upstream's output verbatim.
    - 2+ upstream edges → the whole `{node_id: output}` dict. Merge-style
      nodes that care about provenance can still reach into it; callers
      who only need one branch should use `{{ inputs.<node_id> }}`
      explicitly.
    """
    if not inputs:
        return trigger_data
    if len(inputs) == 1:
        return next(iter(inputs.values()))
    return inputs


async def _dispatch_node(node: PlanNode, inputs: dict, inp: WorkflowRunInput) -> dict:
    """Map a node type to the activity that owns its side effects."""
    if node.type in _TRIGGER_TYPES:
        # Trigger nodes pass the payload through unchanged so downstream
        # templates can use `{{ input.text }}` symmetrically with any other
        # upstream node. No envelope.
        return inp.trigger_data
    single = _single_input(inputs, inp.trigger_data)
    ctx = {"input": single, "inputs": inputs, "trigger": inp.trigger_data}
    if node.type == "template":
        return await workflow.execute_activity(
            render_template_activity,
            args=[node.data.get("template", ""), ctx],
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_node_retry(node.data),
        )
    if node.type == "condition":
        return await workflow.execute_activity(
            evaluate_condition_activity,
            args=[node.data.get("expression", ""), ctx],
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_node_retry(node.data),
        )
    if node.type == "payload_parser":
        return await workflow.execute_activity(
            parse_payload_activity,
            args=[node.data.get("mapping", {}), single],
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_node_retry(node.data),
        )
    if node.type == "merge":
        return await workflow.execute_activity(
            merge_activity, args=[inputs],
            start_to_close_timeout=_ACT_TIMEOUT,
            retry_policy=_node_retry(node.data),
        )
    if node.type == "agent_step":
        # `heartbeat_timeout` is what makes cancel actually reach the
        # activity process — without it, Temporal has no path to deliver
        # the cancel until the activity returns.
        return await workflow.execute_activity(
            run_agent_step_activity,
            args=[
                inp.run_id, node.id, inp.owner_external_id, inp.user_token,
                node.data, inp.trigger_data, inputs, single,
            ],
            start_to_close_timeout=_AGENT_STEP_TIMEOUT,
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=_node_retry(node.data),
        )
    raise ValueError(f"Unknown node type: {node.type}")


async def _set_run(run_id: str, status: str, error: str | None = None) -> None:
    await workflow.execute_activity(
        set_run_status, args=[run_id, status, error],
        start_to_close_timeout=_ACT_TIMEOUT,
        retry_policy=_DEFAULT_RETRY,
    )


async def _set_node(
    run_id: str, node_id: str, node_type: str, status: str,
    input_data: dict | None = None, output_data: dict | None = None,
    error: str | None = None,
) -> None:
    await workflow.execute_activity(
        set_node_status,
        args=[run_id, node_id, node_type, status, input_data, output_data, error],
        start_to_close_timeout=_ACT_TIMEOUT,
        retry_policy=_DEFAULT_RETRY,
    )


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
        await _set_run(inp.run_id, "running")

        try:
            plan = build_topological_plan(inp.definition_snapshot)
        except ValueError as e:
            await _set_run(inp.run_id, "failed", str(e))
            return WorkflowRunResult(status="failed")

        edges = inp.definition_snapshot.get("edges", [])
        context: dict = {}
        skipped: set[str] = set()

        for node in plan:
            should_skip = self._cancelled or node.id in skipped
            if should_skip:
                await _set_node(inp.run_id, node.id, node.type, "skipped")
                continue

            inputs = {src: context.get(src) for src in upstream_of(node.id, edges)}
            await _set_node(inp.run_id, node.id, node.type, "running", input_data=inputs)

            self._current_task = asyncio.ensure_future(_dispatch_node(node, inputs, inp))
            try:
                output = await self._current_task
            except asyncio.CancelledError:
                # Activity was cancelled mid-flight (agent_step aborted its
                # supervisor stream on the way out).
                await _set_node(inp.run_id, node.id, node.type, "skipped")
                continue
            except ActivityError as e:
                # Activity-level cancellation surfaces here (not as
                # asyncio.CancelledError) because Temporal wraps the
                # activity's CancelledError. Treat the node as skipped and
                # let the outer loop finish with "cancelled".
                if isinstance(e.cause, (asyncio.CancelledError, TemporalCancelledError)):
                    await _set_node(inp.run_id, node.id, node.type, "skipped")
                    continue
                # Temporal wraps the real exception — unwrap so the UI sees
                # the real cause (e.g. Jinja UndefinedError, Claude CLI
                # exit 1) rather than the generic "Activity task failed".
                err = str(e.cause) if e.cause else str(e)
                await _set_node(inp.run_id, node.id, node.type, "failed", error=err)
                await _set_run(inp.run_id, "failed", err)
                return WorkflowRunResult(status="failed")
            finally:
                self._current_task = None

            context[node.id] = output
            await _set_node(
                inp.run_id, node.id, node.type, "completed", output_data=output,
            )

            if node.type == "condition" and not output.get("result"):
                for ds in downstream_of(node.id, edges):
                    skipped.add(ds)

        final = "cancelled" if self._cancelled else "completed"
        await _set_run(inp.run_id, final)
        return WorkflowRunResult(status=final)

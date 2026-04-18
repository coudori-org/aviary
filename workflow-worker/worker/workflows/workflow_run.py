"""WorkflowRun — top-level orchestration.

Executes nodes by frontier — every node whose upstream deps are satisfied
runs concurrently, so independent branches don't serialize behind each
other. A failed condition propagates `skipped` to its descendants. A
cancel signal aborts all in-flight nodes (agent steps abort their
supervisor stream on the way out) and marks every later node as skipped.
Fail-fast: the first node failure cancels peers and fails the run.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError as TemporalCancelledError

with workflow.unsafe.imports_passed_through():
    from aviary_shared.workflow_types import WorkflowRunInput, WorkflowRunResult
    from worker.activities.agent_step import (
        ensure_agent_step_session_activity,
        run_agent_step_activity,
        step_session_id,
    )
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
        # the cancel until the activity returns. 60s gives the activity
        # room to breathe under concurrent parallel dispatch (two steps
        # sharing one event loop each sending a full SSE stream); the
        # worker still heartbeats every ~3s so timeout fires only when
        # something is actually wedged.
        return await workflow.execute_activity(
            run_agent_step_activity,
            args=[
                inp.run_id, node.id, inp.owner_external_id, inp.user_token,
                node.data, inp.trigger_data, inputs, single, inp.runtime_endpoint,
                inp.root_run_id or inp.run_id,
            ],
            start_to_close_timeout=_AGENT_STEP_TIMEOUT,
            heartbeat_timeout=timedelta(seconds=60),
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
    error: str | None = None, session_id: str | None = None,
) -> None:
    await workflow.execute_activity(
        set_node_status,
        args=[run_id, node_id, node_type, status, input_data, output_data, error, session_id],
        start_to_close_timeout=_ACT_TIMEOUT,
        retry_policy=_DEFAULT_RETRY,
    )


def _session_id_for(node: PlanNode, run_id: str, root_run_id: str | None) -> str | None:
    """Agent_step nodes own a shared-sessions row computed deterministically
    from (root_run_id, node_id); surfacing it early lets the inspector
    subscribe the moment the step starts running. The root anchor is what
    makes a resumed run's inspector find the ancestor run's transcript
    instead of subscribing to a nonexistent session."""
    if node.type != "agent_step":
        return None
    return step_session_id(run_id, node.id, root_run_id)


@workflow.defn(name="WorkflowRun")
class WorkflowRunWorkflow:
    def __init__(self) -> None:
        self._cancelled = False
        self._active_tasks: set[asyncio.Task] = set()

    @workflow.signal
    def cancel(self) -> None:
        """Cancel the run. Signalling every active task is what actually
        aborts long-running agent_steps mid-stream."""
        self._cancelled = True
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()

    @workflow.run
    async def run(self, inp: WorkflowRunInput) -> WorkflowRunResult:
        await _set_run(inp.run_id, "running")

        try:
            plan = build_topological_plan(inp.definition_snapshot)
        except ValueError as e:
            await _set_run(inp.run_id, "failed", str(e))
            return WorkflowRunResult(status="failed")

        edges = inp.definition_snapshot.get("edges", [])
        nodes_by_id: dict[str, PlanNode] = {n.id: n for n in plan}
        context: dict = {}
        skipped: set[str] = set()
        completed: set[str] = set()
        resume_context = inp.resume_context or {}

        # Seed resume_context: every carried node is already "completed" so
        # frontier scheduling can immediately release its dependents.
        for node in plan:
            if node.id in resume_context:
                carried = resume_context[node.id]
                context[node.id] = carried
                await _set_node(
                    inp.run_id, node.id, node.type, "completed",
                    output_data=carried,
                    session_id=_session_id_for(node, inp.run_id, inp.root_run_id),
                )
                completed.add(node.id)
                if node.type == "condition" and isinstance(carried, dict) and not carried.get("result"):
                    for ds in downstream_of(node.id, edges):
                        skipped.add(ds)

        remaining = {n.id for n in plan} - completed
        failure_error: str | None = None

        async def run_node(node: PlanNode) -> tuple[str, bool, dict | None, str | None]:
            """Return (node_id, ok, output, error_message). A `skipped` or
            cancelled node returns ok=True output=None so the caller can
            branch without exception plumbing."""
            sid = _session_id_for(node, inp.run_id, inp.root_run_id)
            if self._cancelled or node.id in skipped:
                await _set_node(inp.run_id, node.id, node.type, "skipped", session_id=sid)
                return node.id, True, None, None
            inputs = {src: context.get(src) for src in upstream_of(node.id, edges)}
            if node.type == "agent_step":
                # Provision the ``sessions`` row before the inspector hears
                # "running" — otherwise a ChatTranscript that mounts on the
                # status change would 404 before the agent_step activity's
                # own setup runs.
                await workflow.execute_activity(
                    ensure_agent_step_session_activity,
                    args=[inp.run_id, node.id, inp.root_run_id],
                    start_to_close_timeout=_ACT_TIMEOUT,
                    retry_policy=_DEFAULT_RETRY,
                )
            await _set_node(
                inp.run_id, node.id, node.type, "running",
                input_data=inputs, session_id=sid,
            )
            try:
                output = await _dispatch_node(node, inputs, inp)
            except asyncio.CancelledError:
                await _set_node(inp.run_id, node.id, node.type, "skipped", session_id=sid)
                return node.id, True, None, None
            except ActivityError as e:
                if isinstance(e.cause, (asyncio.CancelledError, TemporalCancelledError)):
                    await _set_node(inp.run_id, node.id, node.type, "skipped", session_id=sid)
                    return node.id, True, None, None
                err = str(e.cause) if e.cause else str(e)
                await _set_node(inp.run_id, node.id, node.type, "failed", error=err, session_id=sid)
                return node.id, False, None, err
            await _set_node(
                inp.run_id, node.id, node.type, "completed",
                output_data=output, session_id=sid,
            )
            return node.id, True, output, None

        while remaining and failure_error is None and not self._cancelled:
            frontier = [
                nodes_by_id[nid] for nid in remaining
                if all(
                    src in completed or src in skipped
                    for src in upstream_of(nid, edges)
                )
            ]
            if not frontier:
                # Should not happen once the plan topology is valid, but
                # guard against livelock just in case.
                break

            tasks: dict[asyncio.Task, PlanNode] = {}
            for node in frontier:
                task = asyncio.ensure_future(run_node(node))
                tasks[task] = node
                self._active_tasks.add(task)

            try:
                for task in tasks:
                    node_id, ok, output, err = await task
                    remaining.discard(node_id)
                    node = tasks[task]
                    if not ok:
                        failure_error = err or "node failed"
                        continue
                    if node_id in skipped:
                        continue
                    if output is None:
                        # Skipped-by-cancel path.
                        continue
                    context[node_id] = output
                    completed.add(node_id)
                    if node.type == "condition" and isinstance(output, dict) and not output.get("result"):
                        for ds in downstream_of(node_id, edges):
                            skipped.add(ds)
            finally:
                for task in tasks:
                    self._active_tasks.discard(task)

            if failure_error is not None:
                # Fail-fast: cancel peers already started in this frontier
                # and any still-pending tasks. We've already awaited them in
                # the loop above, so only pending work from other frontiers
                # (there is none — we schedule one frontier at a time) would
                # be hit. Remaining nodes get marked skipped below.
                for nid in remaining:
                    node = nodes_by_id[nid]
                    with contextlib.suppress(Exception):
                        await _set_node(
                            inp.run_id, nid, node.type, "skipped",
                            session_id=_session_id_for(node, inp.run_id, inp.root_run_id),
                        )
                remaining.clear()
                break

        if failure_error is not None:
            await _set_run(inp.run_id, "failed", failure_error)
            return WorkflowRunResult(status="failed")

        if self._cancelled:
            # Any node we never got to gets an explicit skipped status so
            # the UI doesn't show them stuck at pending.
            for nid in remaining:
                node = nodes_by_id[nid]
                with contextlib.suppress(Exception):
                    await _set_node(
                        inp.run_id, nid, node.type, "skipped",
                        session_id=_session_id_for(node, inp.run_id, inp.root_run_id),
                    )
            await _set_run(inp.run_id, "cancelled")
            return WorkflowRunResult(status="cancelled")

        await _set_run(inp.run_id, "completed")
        return WorkflowRunResult(status="completed")

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
    )
    from worker.activities.agent_step_helpers import step_session_id
    from worker.activities.nodes import (
        evaluate_condition_activity,
        merge_activity,
        parse_payload_activity,
        render_template_activity,
    )
    from worker.activities.persistence import set_node_status, set_run_status
    from worker.dag import PlanNode, build_topological_plan, downstream_of, upstream_of


_ACT_TIMEOUT = timedelta(seconds=30)
_AGENT_STEP_TIMEOUT = timedelta(minutes=30)
_AGENT_STEP_HEARTBEAT_TIMEOUT = timedelta(seconds=60)
_TRIGGER_TYPES = {"manual_trigger", "webhook_trigger"}

# Node activities opt into retry via `node.data.retry_count`.
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
    # 0 upstream → trigger payload; 1 → that output verbatim; 2+ → full {node_id: output} dict.
    if not inputs:
        return trigger_data
    if len(inputs) == 1:
        return next(iter(inputs.values()))
    return inputs


async def _dispatch_node(node: PlanNode, inputs: dict, inp: WorkflowRunInput) -> dict:
    if node.type in _TRIGGER_TYPES:
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
        # heartbeat_timeout is required for cancel delivery; 60s absorbs parallel-dispatch starvation.
        return await workflow.execute_activity(
            run_agent_step_activity,
            args=[
                inp.run_id, node.id, inp.owner_external_id, inp.user_token,
                node.data, inp.trigger_data, inputs, single, inp.runtime_endpoint,
                inp.root_run_id or inp.run_id,
            ],
            start_to_close_timeout=_AGENT_STEP_TIMEOUT,
            heartbeat_timeout=_AGENT_STEP_HEARTBEAT_TIMEOUT,
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


def _session_ids(plan: list[PlanNode], run_id: str, root_run_id: str | None) -> dict[str, str | None]:
    return {
        n.id: (step_session_id(run_id, n.id, root_run_id) if n.type == "agent_step" else None)
        for n in plan
    }


@workflow.defn(name="WorkflowRun")
class WorkflowRunWorkflow:
    def __init__(self) -> None:
        self._cancelled = False
        self._active_tasks: set[asyncio.Task] = set()

    @workflow.signal
    def cancel(self) -> None:
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
        session_ids = _session_ids(plan, inp.run_id, inp.root_run_id)
        context: dict = {}
        skipped: set[str] = set()
        completed: set[str] = set()
        resume_context = inp.resume_context or {}

        async def _skip(nid: str) -> None:
            node = nodes_by_id[nid]
            with contextlib.suppress(Exception):
                await _set_node(
                    inp.run_id, nid, node.type, "skipped",
                    session_id=session_ids.get(nid),
                )

        # Carried nodes start completed so the frontier releases their dependents.
        for node in plan:
            if node.id not in resume_context:
                continue
            carried = resume_context[node.id]
            context[node.id] = carried
            await _set_node(
                inp.run_id, node.id, node.type, "completed",
                output_data=carried, session_id=session_ids.get(node.id),
            )
            completed.add(node.id)
            if node.type == "condition" and isinstance(carried, dict) and not carried.get("result"):
                for ds in downstream_of(node.id, edges):
                    skipped.add(ds)

        remaining = {n.id for n in plan} - completed
        failure_error: str | None = None

        async def run_node(node: PlanNode) -> tuple[str, bool, dict | None, str | None]:
            sid = session_ids.get(node.id)
            if self._cancelled or node.id in skipped:
                await _set_node(inp.run_id, node.id, node.type, "skipped", session_id=sid)
                return node.id, True, None, None
            inputs = {src: context.get(src) for src in upstream_of(node.id, edges)}
            if node.type == "agent_step":
                # Provision the sessions row before "running" so the
                # inspector's ChatTranscript doesn't 404 between status
                # publish and the activity's own setup.
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
                if all(src in completed or src in skipped for src in upstream_of(nid, edges))
            ]
            if not frontier:
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
                    if node_id in skipped or output is None:
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
                for nid in list(remaining):
                    await _skip(nid)
                remaining.clear()
                break

        if failure_error is not None:
            await _set_run(inp.run_id, "failed", failure_error)
            return WorkflowRunResult(status="failed")

        if self._cancelled:
            for nid in list(remaining):
                await _skip(nid)
            await _set_run(inp.run_id, "cancelled")
            return WorkflowRunResult(status="cancelled")

        await _set_run(inp.run_id, "completed")
        return WorkflowRunResult(status="completed")

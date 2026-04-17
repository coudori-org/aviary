"""WorkflowRun — top-level orchestration.

Executes nodes in topological order, threading each node's output into a
shared context so downstream nodes can reference upstream payloads. A
failed condition propagates `skipped` to its descendants. A cancel signal
stops scheduling new nodes; any in-flight activity is allowed to finish.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from aviary_shared.workflow_types import WorkflowRunInput, WorkflowRunResult
    from worker.activities.nodes import (
        evaluate_condition_activity,
        merge_activity,
        parse_payload_activity,
        render_template_activity,
    )
    from worker.activities.persistence import set_node_status, set_run_status
    from worker.dag import PlanNode, build_topological_plan, downstream_of, upstream_of


_ACT_TIMEOUT = timedelta(seconds=30)
_TRIGGER_TYPES = {"manual_trigger", "webhook_trigger"}


async def _dispatch_node(node: PlanNode, inputs: dict, trigger_data: dict) -> dict:
    """Map a node type to the activity that owns its side effects."""
    if node.type in _TRIGGER_TYPES:
        return {"payload": trigger_data}
    ctx = {"inputs": inputs, "trigger": trigger_data}
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
        source = next(iter(inputs.values())) if inputs else trigger_data
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
        # Phase 9 wires this to the supervisor.
        raise RuntimeError("agent_step activity not implemented yet")
    raise ValueError(f"Unknown node type: {node.type}")


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

            try:
                output = await _dispatch_node(node, inputs, inp.trigger_data)
            except Exception as e:  # noqa: BLE001 — surface to DB + WS
                err = str(e)
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

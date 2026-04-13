"""Workflow DAG execution engine.

Runs as an asyncio.Task in the API server process (same pattern as stream_manager).
Executes nodes in topological order with fan-out parallelism.
Publishes real-time status to Redis pub/sub for WebSocket relay.
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from aviary_shared.db.models import WorkflowRun, WorkflowNodeRun
from app.db.session import async_session_factory
from app.services import agent_supervisor, redis_service

logger = logging.getLogger(__name__)

_active_runs: dict[str, asyncio.Task] = {}


def _channel(run_id: str) -> str:
    return f"workflow_run:{run_id}"


async def _publish(run_id: str, event: dict) -> None:
    client = redis_service.get_client()
    if not client:
        return
    try:
        await client.publish(_channel(run_id), json.dumps(event))
    except Exception:
        logger.warning("Redis publish failed for run %s", run_id, exc_info=True)


# ── DAG helpers ──

def _topo_levels(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    """Return nodes grouped by topological level (parallel execution within a level)."""
    node_ids = {n["id"] for n in nodes}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    children: dict[str, list[str]] = defaultdict(list)

    for e in edges:
        src, tgt = e["source"], e["target"]
        if src in node_ids and tgt in node_ids:
            in_degree[tgt] = in_degree.get(tgt, 0) + 1
            children[src].append(tgt)

    levels: list[list[str]] = []
    queue = [nid for nid, deg in in_degree.items() if deg == 0]

    while queue:
        levels.append(queue)
        next_queue: list[str] = []
        for nid in queue:
            for child in children.get(nid, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    next_queue.append(child)
        queue = next_queue

    return levels


def _gather_inputs(node_id: str, edges: list[dict], outputs: dict[str, dict]) -> dict:
    """Collect outputs from all upstream nodes connected to this node."""
    result = {}
    for e in edges:
        if e["target"] == node_id and e["source"] in outputs:
            result[e["source"]] = outputs[e["source"]]
    return result


# ── Node executors ──

async def _exec_trigger(node: dict, trigger_data: dict) -> dict:
    return {"output": trigger_data}


async def _exec_agent_step(
    node: dict, input_data: dict, worker_agent_id: str, run_id: str,
) -> dict:
    """Execute an Agent Step by sending a message to the worker agent pod."""
    data = node.get("data", {})
    prompt_template = data.get("prompt_template", "{{input}}")
    instruction = data.get("instruction", "")
    model_config = data.get("model_config", {})
    output_schema = data.get("output_schema")

    # Resolve template
    input_text = json.dumps(input_data, ensure_ascii=False) if input_data else ""
    prompt = prompt_template.replace("{{input}}", input_text)

    # Create ephemeral session
    session_id = str(uuid.uuid4())

    try:
        await agent_supervisor.ensure_agent_running(agent_id=worker_agent_id, owner_id="")
        ready = await agent_supervisor.wait_for_agent_ready(worker_agent_id, timeout=90)
        if not ready:
            raise RuntimeError(
                "Worker agent Pod did not become ready within 90s. "
                "Check that the K8s cluster is running and the runtime image is loaded."
            )
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"Agent Supervisor connection failed: {e}. "
            "Ensure the agent-supervisor is running (port 9000) and reachable."
        ) from e

    stream_url = agent_supervisor.get_stream_url(worker_agent_id, session_id)
    if not model_config.get("backend") or not model_config.get("model"):
        raise RuntimeError(
            "Agent Step has no model configured. "
            "Set backend and model in the Agent Step node's inspector panel."
        )

    full_response = ""
    structured_output = None

    request_body: dict = {
        "content_parts": [{"text": prompt}],
        "session_id": session_id,
        "model_config_data": model_config,
        "agent_config": {
            "instruction": instruction,
            "tools": [],
            "mcp_servers": {},
            "policy": {},
        },
    }
    if output_schema:
        request_body["output_format"] = output_schema

    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            stream_url,
            json=request_body,
            timeout=None,
        ) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise RuntimeError(f"Agent runtime returned HTTP {resp.status_code}: {body.decode(errors='replace')[:500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = json.loads(line[6:])
                chunk_type = chunk.get("type")

                if chunk_type == "chunk":
                    text = chunk.get("content", "")
                    full_response += text
                    await _publish(run_id, {
                        "type": "node_log",
                        "node_id": node["id"],
                        "log_type": "chunk",
                        "content": text,
                    })
                elif chunk_type == "thinking":
                    await _publish(run_id, {
                        "type": "node_log",
                        "node_id": node["id"],
                        "log_type": "thinking",
                        "content": chunk.get("content", ""),
                    })
                elif chunk_type == "tool_use":
                    await _publish(run_id, {
                        "type": "node_log",
                        "node_id": node["id"],
                        "log_type": "tool_use",
                        "name": chunk.get("name"),
                        "input": chunk.get("input"),
                    })
                elif chunk_type == "tool_result":
                    await _publish(run_id, {
                        "type": "node_log",
                        "node_id": node["id"],
                        "log_type": "tool_result",
                        "content": chunk.get("content", ""),
                    })
                elif chunk_type == "result":
                    so = chunk.get("structured_output")
                    if so is not None:
                        structured_output = so
                elif chunk_type == "error":
                    raise RuntimeError(chunk.get("message", "Agent runtime error"))

    if structured_output is not None:
        # Best-effort session cleanup
        try:
            await agent_supervisor.cleanup_session(worker_agent_id, session_id)
        except Exception:
            pass
        return {"output": structured_output}

    if not full_response.strip():
        raise RuntimeError("Agent Step produced no output — the LLM may be unreachable or the request failed silently")

    # Best-effort session cleanup
    try:
        await agent_supervisor.cleanup_session(worker_agent_id, session_id)
    except Exception:
        pass

    return {"output": full_response}


async def _exec_condition(node: dict, input_data: dict) -> dict:
    """Evaluate a condition expression against input data."""
    expression = node.get("data", {}).get("expression", "")
    if not expression:
        return {"branch": "true"}

    # Simple evaluation: check if expression is truthy in context of input
    # For safety, only support basic string operations
    input_str = json.dumps(input_data, ensure_ascii=False)
    try:
        if ".contains(" in expression:
            # Parse: output.contains("keyword")
            keyword = expression.split('.contains("')[1].rstrip('")')
            result = keyword.lower() in input_str.lower()
        elif expression.strip().lower() in ("true", "1", "yes"):
            result = True
        elif expression.strip().lower() in ("false", "0", "no"):
            result = False
        else:
            result = bool(input_str)
    except Exception:
        result = False

    return {"branch": "true" if result else "false"}


async def _exec_merge(node: dict, input_data: dict) -> dict:
    return {"output": input_data}


async def _exec_payload_parser(node: dict, input_data: dict) -> dict:
    mapping = node.get("data", {}).get("mapping", {})
    if not mapping:
        return {"output": input_data}

    # Flatten all upstream outputs into one dict
    flat: dict = {}
    for src_output in input_data.values():
        if isinstance(src_output, dict):
            out = src_output.get("output", src_output)
            if isinstance(out, dict):
                flat.update(out)
            elif isinstance(out, str):
                try:
                    flat.update(json.loads(out))
                except (json.JSONDecodeError, TypeError):
                    flat["_raw"] = out

    result = {}
    for target_key, source_path in mapping.items():
        result[target_key] = flat.get(source_path)
    return {"output": result}


async def _exec_template(node: dict, input_data: dict) -> dict:
    template = node.get("data", {}).get("template", "")
    result = template

    # Build label→output mapping from input_data keys (node IDs)
    # input_data is keyed by source node ID, each value is the node's output dict
    all_outputs: list[str] = []
    for src_id, src_output in input_data.items():
        out_text = ""
        if isinstance(src_output, dict):
            out_text = src_output.get("output", "")
            if not isinstance(out_text, str):
                out_text = json.dumps(out_text, ensure_ascii=False)
        else:
            out_text = str(src_output)

        # Replace by node ID: {{agent_step_1234}}
        result = result.replace(f"{{{{{src_id}}}}}", out_text)
        all_outputs.append(out_text)

    # Replace {{input}} with all upstream outputs joined
    if "{{input}}" in result:
        result = result.replace("{{input}}", "\n\n".join(all_outputs))

    return {"output": result}


# ── Main executor ──

NODE_EXECUTORS = {
    "manual_trigger": _exec_trigger,
    "webhook_trigger": _exec_trigger,
    "condition": _exec_condition,
    "merge": _exec_merge,
    "payload_parser": _exec_payload_parser,
    "template": _exec_template,
}


async def _execute_node(
    run_id: str,
    node: dict,
    input_data: dict,
    worker_agent_id: str | None,
    trigger_data: dict,
) -> dict:
    """Execute a single node and return its output."""
    node_type = node.get("type", "")

    if node_type in ("manual_trigger", "webhook_trigger"):
        return await _exec_trigger(node, trigger_data)
    elif node_type == "agent_step":
        if not worker_agent_id:
            raise RuntimeError("No worker agent configured for this workflow")
        return await _exec_agent_step(node, input_data, worker_agent_id, run_id)
    elif node_type in NODE_EXECUTORS:
        return await NODE_EXECUTORS[node_type](node, input_data)
    else:
        raise RuntimeError(f"Unknown node type: {node_type}")


async def execute_run(
    run_id: str,
    workflow_id: str,
    worker_agent_id: str | None,
    trigger_data: dict,
) -> None:
    """Background task: execute a workflow run."""
    run_uuid = uuid.UUID(run_id)

    try:
        # Load run and parse definition
        async with async_session_factory() as db:

            result = await db.execute(
                select(WorkflowRun).where(WorkflowRun.id == run_uuid)
            )
            run = result.scalar_one_or_none()
            if not run:
                return

            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            await db.commit()

        definition = run.definition_snapshot
        nodes_list: list[dict] = definition.get("nodes", [])
        edges_list: list[dict] = definition.get("edges", [])
        nodes_by_id = {n["id"]: n for n in nodes_list}

        await _publish(run_id, {"type": "run_status", "status": "running"})

        # Topological execution
        levels = _topo_levels(nodes_list, edges_list)
        outputs: dict[str, dict] = {}

        for level in levels:
            async def run_node(node_id: str) -> None:
                node = nodes_by_id[node_id]
                node_type = node.get("type", "")
                input_data = _gather_inputs(node_id, edges_list, outputs)

                # For condition nodes, check if this node should be skipped
                # based on upstream condition branches
                should_skip = False
                for e in edges_list:
                    if e["target"] == node_id and e["source"] in outputs:
                        src_output = outputs[e["source"]]
                        src_node = nodes_by_id.get(e["source"], {})
                        if src_node.get("type") == "condition":
                            branch = src_output.get("branch", "true")
                            edge_handle = e.get("sourceHandle", "out-0")
                            expected_handle = "out-0" if branch == "true" else "out-1"
                            if edge_handle != expected_handle:
                                should_skip = True
                                break

                # Create node run record
                async with async_session_factory() as db:
                    node_run = WorkflowNodeRun(
                        run_id=run_uuid,
                        node_id=node_id,
                        node_type=node_type,
                        status="skipped" if should_skip else "running",
                        input_data=input_data if input_data else None,
                        started_at=datetime.now(timezone.utc),
                    )
                    db.add(node_run)
                    await db.commit()
                    node_run_id = node_run.id

                await _publish(run_id, {
                    "type": "node_status",
                    "node_id": node_id,
                    "node_type": node_type,
                    "status": "skipped" if should_skip else "running",
                    "input_data": input_data if input_data else None,
                })

                if should_skip:
                    outputs[node_id] = {"skipped": True}
                    return

                try:
                    output = await _execute_node(
                        run_id, node, input_data, worker_agent_id, trigger_data,
                    )
                    outputs[node_id] = output

                    async with async_session_factory() as db:

                        await db.execute(
                            update(WorkflowNodeRun)
                            .where(WorkflowNodeRun.id == node_run_id)
                            .values(
                                status="completed",
                                output_data=output,
                                completed_at=datetime.now(timezone.utc),
                            )
                        )
                        await db.commit()

                    await _publish(run_id, {
                        "type": "node_status",
                        "node_id": node_id,
                        "status": "completed",
                        "output_data": output,
                    })

                except Exception as exc:
                    error_msg = str(exc)
                    outputs[node_id] = {"error": error_msg}

                    async with async_session_factory() as db:

                        await db.execute(
                            update(WorkflowNodeRun)
                            .where(WorkflowNodeRun.id == node_run_id)
                            .values(
                                status="failed",
                                error=error_msg,
                                completed_at=datetime.now(timezone.utc),
                            )
                        )
                        await db.commit()

                    await _publish(run_id, {
                        "type": "node_status",
                        "node_id": node_id,
                        "status": "failed",
                        "error": error_msg,
                    })
            # Execute nodes at this level in parallel, wait for ALL to finish
            await asyncio.gather(*[run_node(nid) for nid in level])
            # If any node in this level failed, stop executing further levels
            level_failed = any(
                isinstance(outputs.get(nid), dict) and "error" in outputs.get(nid, {})
                for nid in level
            )
            if level_failed:
                break

        # Determine final status
        any_failed = any(
            isinstance(o, dict) and "error" in o
            for o in outputs.values()
        )
        final_status = "failed" if any_failed else "completed"

        async with async_session_factory() as db:

            await db.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_uuid)
                .values(
                    status=final_status,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        await _publish(run_id, {"type": "run_status", "status": final_status})

    except asyncio.CancelledError:
        logger.info("Run cancelled: %s", run_id)
        async with async_session_factory() as db:

            await db.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_uuid)
                .values(status="cancelled", completed_at=datetime.now(timezone.utc))
            )
            await db.commit()
        await _publish(run_id, {"type": "run_status", "status": "cancelled"})

    except Exception as exc:
        logger.exception("Run failed: %s", run_id)
        async with async_session_factory() as db:

            await db.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_uuid)
                .values(
                    status="failed",
                    error=str(exc),
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        await _publish(run_id, {"type": "run_status", "status": "failed", "error": str(exc)})

    finally:
        _active_runs.pop(run_id, None)


def start_run(
    run_id: str,
    workflow_id: str,
    worker_agent_id: str | None,
    trigger_data: dict,
) -> None:
    """Launch a workflow run as a background task."""
    existing = _active_runs.get(run_id)
    if existing and not existing.done():
        return

    task = asyncio.create_task(
        execute_run(run_id, workflow_id, worker_agent_id, trigger_data)
    )
    _active_runs[run_id] = task


def cancel_run(run_id: str) -> bool:
    """Cancel an active run."""
    task = _active_runs.get(run_id)
    if not task or task.done():
        return False
    task.cancel()
    return True


def is_running(run_id: str) -> bool:
    task = _active_runs.get(run_id)
    return task is not None and not task.done()

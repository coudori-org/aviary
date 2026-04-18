"""Workflow run orchestration.

Couples the DB row (authoritative source for owners / history) with the
Temporal workflow handle. Trigger path: insert pending row → start Temporal
workflow reusing the row id as the workflow_id. Cancel path: signal + short
grace period + force-terminate on timeout, all synchronous inside the
request — no background tasks (uvicorn hot-reload hates them).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User, Workflow, WorkflowNodeRun, WorkflowRun, WorkflowVersion
from app.db.session import async_session_factory
from app.schemas.workflow import WorkflowRunCreate
from app.services import redis_service, temporal_client
from aviary_shared.workflow_types import WorkflowRunInput

logger = logging.getLogger(__name__)

_CANCEL_POLL_INTERVAL = 0.5
_CANCEL_POLL_ATTEMPTS = 10  # ~5s total — long enough for graceful shutdown


async def _latest_version(db: AsyncSession, workflow_id: uuid.UUID) -> WorkflowVersion | None:
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _validate_artifact_name_uniqueness(definition: dict) -> None:
    """Reject runs where a downstream node has multiple upstreams producing
    the same artifact name — the pre-copy target would collide at
    `/workspace/{name}`."""
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    produces: dict[str, set[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        data = node.get("data") or {}
        names = {
            a.get("name")
            for a in (data.get("artifacts") or [])
            if isinstance(a, dict) and isinstance(a.get("name"), str)
        }
        names.discard(None)
        if isinstance(nid, str) and names:
            produces[nid] = names

    upstream: dict[str, list[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        src, tgt = edge.get("source"), edge.get("target")
        if isinstance(src, str) and isinstance(tgt, str):
            upstream.setdefault(tgt, []).append(src)

    for target, sources in upstream.items():
        seen: dict[str, str] = {}
        for src in sources:
            for name in produces.get(src, ()):  # type: ignore[union-attr]
                if name in seen and seen[name] != src:
                    raise ValueError(
                        f"Artifact name collision at node '{target}': both "
                        f"'{seen[name]}' and '{src}' declare artifact '{name}'",
                    )
                seen[name] = src


async def create_run(
    db: AsyncSession, workflow: Workflow, user: User, body: WorkflowRunCreate,
    user_token: str | None = None,
) -> WorkflowRun:
    """Insert the run row, hand off to Temporal, return the persisted row.

    Raises `ValueError` when the caller asks for a deployed run but no
    version has been published yet. Router converts this to HTTP 400.
    """
    if body.run_type == "deployed":
        version = await _latest_version(db, workflow.id)
        if version is None:
            raise ValueError("Workflow has no deployed version yet")
        definition_snapshot = version.definition
        version_id = version.id
    else:
        definition_snapshot = workflow.definition
        version_id = None

    _validate_artifact_name_uniqueness(definition_snapshot)

    run = WorkflowRun(
        workflow_id=workflow.id,
        version_id=version_id,
        run_type=body.run_type,
        trigger_type=body.trigger_type,
        trigger_data=body.trigger_data or {},
        triggered_by=user.id,
        status="pending",
        definition_snapshot=definition_snapshot,
    )
    db.add(run)
    await db.flush()
    # Commit before starting Temporal so the worker's persistence activity
    # (which updates this row by id) always sees it.
    await db.commit()

    temporal_run_id = await temporal_client.start_workflow_run(
        WorkflowRunInput(
            run_id=str(run.id),
            owner_external_id=user.external_id,
            definition_snapshot=definition_snapshot,
            trigger_data=body.trigger_data or {},
            user_token=user_token,
            runtime_endpoint=workflow.runtime_endpoint,
            root_run_id=str(run.id),
        )
    )
    run.temporal_run_id = temporal_run_id
    await db.commit()
    await db.refresh(run)
    return run


async def cancel_run(run: WorkflowRun) -> None:
    """Cooperative cancel → poll briefly → force-terminate on timeout.

    Three cases, all resolved before the request returns:
      1. Temporal workflow is already gone (externally terminated, expired)
         → reconcile DB row so the UI doesn't stay "Running".
      2. Signal lands within the grace window → worker's persistence activity
         writes `cancelled` to DB. Nothing else to do.
      3. Workflow is wedged (e.g. activation-failure loop) → signal queues
         forever; we terminate and write DB ourselves.
    """
    run_id = str(run.id)

    if not await temporal_client.workflow_still_running(run_id):
        await _mark_run_cancelled(run_id, error="workflow no longer running in Temporal")
        return

    await temporal_client.cancel_workflow_run(run_id)

    for _ in range(_CANCEL_POLL_ATTEMPTS):
        await asyncio.sleep(_CANCEL_POLL_INTERVAL)
        if not await temporal_client.workflow_still_running(run_id):
            # Worker processed the signal and wrote the final DB status via
            # its persistence activity. Confirm the row is reconciled in
            # case the worker crashed mid-write.
            await _mark_run_cancelled(run_id, error="reconciled after graceful cancel")
            return

    if await temporal_client.terminate_workflow_run(
        run_id, reason="cancel signal not processed within grace period",
    ):
        await _mark_run_cancelled(
            run_id, error="force-terminated after cancel signal stalled",
        )


async def _mark_run_cancelled(run_id: str, error: str) -> None:
    """Reconcile run + any still-running node rows.

    Graceful cancel path has the worker mark each in-flight node as
    `skipped` before it exits, matching the Temporal cancel semantics.
    Force-terminate bypasses worker code, so we do the same sweep here
    to avoid leaving node_runs stuck at `running`.
    """
    now = datetime.now(timezone.utc)
    run_uuid = uuid.UUID(run_id)
    async with async_session_factory() as session:
        run_result = await session.execute(
            update(WorkflowRun)
            .where(
                WorkflowRun.id == run_uuid,
                WorkflowRun.status.in_(("pending", "running")),
            )
            .values(status="cancelled", completed_at=now, error=error)
        )
        node_result = await session.execute(
            update(WorkflowNodeRun)
            .where(
                WorkflowNodeRun.run_id == run_uuid,
                WorkflowNodeRun.status.in_(("pending", "running")),
            )
            .values(status="skipped", completed_at=now)
        )
        await session.commit()

    if not run_result.rowcount and not node_result.rowcount:
        return
    client = redis_service.get_client()
    if not client:
        return
    channel = f"workflow:run:{run_id}:events"
    try:
        if run_result.rowcount:
            await client.publish(
                channel,
                json.dumps({"type": "run_status", "status": "cancelled", "error": error}),
            )
    except Exception:
        logger.warning("publish cancelled event failed", exc_info=True)


async def resume_run(
    db: AsyncSession, workflow: Workflow, source_run: WorkflowRun, user: User,
    user_token: str | None = None,
) -> WorkflowRun:
    # Resume inherits the source's type + definition so the carried-over
    # outputs stay bound to the graph they were produced against:
    #   draft source    → draft resume off the live workflow.definition
    #   deployed source → deployed resume pinned to the SOURCE's version,
    #                     not the latest (the user might have since moved
    #                     the workflow forward to v3; resuming a v1 run
    #                     against v3 would mismatch completed outputs).
    if source_run.run_type == "deployed":
        if source_run.version_id is None:
            raise ValueError("Deployed source run has no version pin")
        version = (await db.execute(
            select(WorkflowVersion).where(WorkflowVersion.id == source_run.version_id)
        )).scalar_one_or_none()
        if version is None:
            raise ValueError("Source version no longer exists")
        definition_snapshot = version.definition
        new_run_type = "deployed"
        new_version_id = version.id
    else:
        definition_snapshot = workflow.definition
        new_run_type = "draft"
        new_version_id = None

    _validate_artifact_name_uniqueness(definition_snapshot)
    live_node_ids = {
        n["id"] for n in definition_snapshot.get("nodes", [])
        if isinstance(n, dict) and isinstance(n.get("id"), str)
    }

    source = await get_run(db, source_run.id, with_nodes=True)
    resume_context = {
        nr.node_id: nr.output_data
        for nr in (source.node_runs or [])
        if nr.status == "completed" and nr.node_id in live_node_ids
    }

    # Resume only makes sense when there's work left — either failed /
    # cancelled nodes from the source, or new nodes the user added after
    # the source finished. If every live node already has a completed
    # output carried forward, there's nothing to run.
    if live_node_ids and set(resume_context.keys()) >= live_node_ids:
        raise ValueError(
            "Nothing to resume — every node in the current workflow is already "
            "completed in this run",
        )

    root_run_id = source_run.root_run_id or source_run.id
    run = WorkflowRun(
        workflow_id=workflow.id,
        version_id=new_version_id,
        run_type=new_run_type,
        trigger_type=source_run.trigger_type,
        trigger_data=source_run.trigger_data or {},
        triggered_by=user.id,
        status="pending",
        definition_snapshot=definition_snapshot,
        root_run_id=root_run_id,
    )
    db.add(run)
    await db.flush()
    await db.commit()

    temporal_run_id = await temporal_client.start_workflow_run(
        WorkflowRunInput(
            run_id=str(run.id),
            owner_external_id=user.external_id,
            definition_snapshot=definition_snapshot,
            trigger_data=source_run.trigger_data or {},
            user_token=user_token,
            runtime_endpoint=workflow.runtime_endpoint,
            resume_context=resume_context,
            root_run_id=str(root_run_id),
        )
    )
    run.temporal_run_id = temporal_run_id
    await db.commit()
    await db.refresh(run)
    return run


async def get_run(
    db: AsyncSession, run_id: uuid.UUID, with_nodes: bool = False,
) -> WorkflowRun | None:
    stmt = select(WorkflowRun).where(WorkflowRun.id == run_id)
    if with_nodes:
        stmt = stmt.options(selectinload(WorkflowRun.node_runs))
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_runs(
    db: AsyncSession, workflow_id: uuid.UUID,
    *,
    run_type: str | None = None,
    include_drafts: bool = False,
    version_id: uuid.UUID | None = None,
    offset: int = 0, limit: int = 50,
) -> tuple[list[WorkflowRun], int]:
    """List runs for a workflow.

    ``run_type`` is the preferred filter — pass "draft" or "deployed"
    to get only that type. ``include_drafts`` stays as a backwards-
    compatible shorthand: omit both → deployed-only (old default),
    include_drafts=True → both types (sidebar uses this path today).
    """
    base = select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
    if run_type is not None:
        base = base.where(WorkflowRun.run_type == run_type)
    elif not include_drafts:
        base = base.where(WorkflowRun.run_type == "deployed")
    if version_id is not None:
        base = base.where(WorkflowRun.version_id == version_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(
        base.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit)
    )
    return list(result.scalars().all()), total

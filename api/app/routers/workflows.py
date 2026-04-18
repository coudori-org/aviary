"""Workflow CRUD + deploy/edit/versions + run trigger/cancel/list/WS."""

import asyncio
import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_session_data, require_workflow_owner
from app.auth.oidc import validate_token
from app.auth.session_store import SESSION_COOKIE_NAME, SessionData, get_fresh_session
from app.config import settings
from app.db.models import User, Workflow
from app.db.session import async_session_factory, get_db
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowRunCreate,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowUpdate,
    WorkflowVersionResponse,
)
from app.schemas.workflow_assistant import (
    WorkflowAssistantRequest,
    WorkflowAssistantResponse,
)
from app.services import (
    redis_service,
    workflow_assistant_service,
    workflow_run_service,
    workflow_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workflows, total = await workflow_service.list_workflows_for_user(db, user, offset, limit)
    items = []
    for w in workflows:
        cv = await workflow_service.current_version_number(db, w.id)
        items.append(WorkflowResponse.from_orm_workflow(w, current_version=cv))
    return WorkflowListResponse(items=items, total=total)


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: WorkflowCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow = await workflow_service.create_workflow(db, user, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return WorkflowResponse.from_orm_workflow(workflow)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    cv = await workflow_service.current_version_number(db, workflow.id)
    return WorkflowResponse.from_orm_workflow(workflow, current_version=cv)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    body: WorkflowUpdate,
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    workflow = await workflow_service.update_workflow(db, workflow, body)
    await db.refresh(workflow)
    cv = await workflow_service.current_version_number(db, workflow.id)
    return WorkflowResponse.from_orm_workflow(workflow, current_version=cv)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    await workflow_service.delete_workflow(db, workflow)
    return None


@router.post("/{workflow_id}/deploy", response_model=WorkflowVersionResponse)
async def deploy_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    version = await workflow_service.deploy_workflow(db, workflow, user)
    await db.refresh(version)
    return WorkflowVersionResponse.from_orm_version(version)


@router.post("/{workflow_id}/edit", response_model=WorkflowResponse)
async def edit_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    workflow = await workflow_service.mark_workflow_draft(db, workflow)
    await db.refresh(workflow)
    cv = await workflow_service.current_version_number(db, workflow.id)
    return WorkflowResponse.from_orm_workflow(workflow, current_version=cv)


@router.post("/{workflow_id}/cancel-edit", response_model=WorkflowResponse)
async def cancel_edit_workflow(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    """Abandon the current draft and snap back to the latest deployed
    version — inverse of `POST /edit`. Fails 400 if the workflow has
    never been deployed (nothing to revert to)."""
    try:
        workflow = await workflow_service.cancel_edit(db, workflow)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e),
        ) from e
    await db.refresh(workflow)
    cv = await workflow_service.current_version_number(db, workflow.id)
    return WorkflowResponse.from_orm_workflow(workflow, current_version=cv)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_workflow_versions(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    versions = await workflow_service.list_workflow_versions(db, workflow.id)
    return [WorkflowVersionResponse.from_orm_version(v) for v in versions]


# ── AI Assistant ────────────────────────────────────────────────────────────


_ASSISTANT_POLL_SECONDS = 0.25


@router.post("/{workflow_id}/assistant/stream")
async def workflow_assistant_stream(
    body: WorkflowAssistantRequest,
    workflow: Workflow = Depends(require_workflow_owner()),
    session_data: SessionData = Depends(get_session_data),
):
    """SSE stream of the assistant's turn.

    Pre-subscribes to the supervisor's `session:{sid}:events` channel so
    we catch every `chunk`/`thinking`/`tool_use`/`tool_result` from the
    moment the runtime starts emitting. Terminates with a synthetic
    `assistant_done` event carrying the parsed plan (if any), or `error`.
    """
    session_id = str(uuid.uuid4())
    pubsub = await redis_service.subscribe(session_id)
    if pubsub is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        )

    async def generate():
        task = asyncio.create_task(
            workflow_assistant_service.ask(
                workflow, body,
                user_token=session_data.access_token,
                session_id=session_id,
            ),
        )
        try:
            # Forward supervisor events until the service call finishes,
            # then drain any events still in flight before emitting the
            # terminal frame.
            while not task.done():
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_ASSISTANT_POLL_SECONDS,
                )
                if msg and msg.get("type") == "message":
                    yield f"data: {msg['data']}\n\n"

            for _ in range(20):
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.05,
                )
                if not msg:
                    break
                if msg.get("type") == "message":
                    yield f"data: {msg['data']}\n\n"

            try:
                response = task.result()
                done_event = {
                    "type": "assistant_done",
                    "reply": response.reply,
                    "plan": [op.model_dump(mode="json") for op in response.plan],
                }
                yield f"data: {json.dumps(done_event)}\n\n"
            except HTTPException as e:
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": str(e.detail)})
                    + "\n\n"
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("Workflow assistant stream failed")
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": str(e) or "Assistant failed"})
                    + "\n\n"
                )
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(Exception):
                    await task
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Runs ────────────────────────────────────────────────────────────────────

@router.post("/{workflow_id}/runs", response_model=WorkflowRunResponse, status_code=status.HTTP_201_CREATED)
async def trigger_run(
    body: WorkflowRunCreate,
    workflow: Workflow = Depends(require_workflow_owner()),
    user: User = Depends(get_current_user),
    session_data: SessionData = Depends(get_session_data),
    db: AsyncSession = Depends(get_db),
):
    try:
        run = await workflow_run_service.create_run(
            db, workflow, user, body, user_token=session_data.access_token,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return WorkflowRunResponse.from_orm_run(run)


@router.get("/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def list_runs(
    run_type: str | None = Query(None, pattern="^(draft|deployed)$"),
    include_drafts: bool = Query(False),
    version_id: uuid.UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    runs, total = await workflow_run_service.list_runs(
        db, workflow.id,
        run_type=run_type,
        include_drafts=include_drafts,
        version_id=version_id, offset=offset, limit=limit,
    )
    return WorkflowRunListResponse(
        items=[WorkflowRunResponse.from_orm_run(r) for r in runs],
        total=total,
    )


@router.get("/{workflow_id}/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_run(
    run_id: uuid.UUID,
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    run = await workflow_run_service.get_run(db, run_id, with_nodes=True)
    if run is None or run.workflow_id != workflow.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return WorkflowRunResponse.from_orm_run(run, include_node_runs=True)


@router.post("/{workflow_id}/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(
    run_id: uuid.UUID,
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    run = await workflow_run_service.get_run(db, run_id)
    if run is None or run.workflow_id != workflow.id:
        raise HTTPException(status_code=404, detail="Run not found")
    await workflow_run_service.cancel_run(run)
    return {"ok": True}


@router.post(
    "/{workflow_id}/runs/{run_id}/resume",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def resume_run(
    run_id: uuid.UUID,
    workflow: Workflow = Depends(require_workflow_owner()),
    user: User = Depends(get_current_user),
    session_data: SessionData = Depends(get_session_data),
    db: AsyncSession = Depends(get_db),
):
    source = await workflow_run_service.get_run(db, run_id)
    if source is None or source.workflow_id != workflow.id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        new_run = await workflow_run_service.resume_run(
            db, workflow, source, user, user_token=session_data.access_token,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return WorkflowRunResponse.from_orm_run(new_run)


# ── Run WebSocket ───────────────────────────────────────────────────────────

_TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


@router.websocket("/{workflow_id}/runs/{run_id}/ws")
async def workflow_run_ws(websocket: WebSocket, workflow_id: uuid.UUID, run_id: uuid.UUID):
    """Stream a live run's events to a connected client.

    Completed runs have nothing to stream — the client should read the
    final state via `GET /workflows/{id}/runs/{run_id}` instead. If a
    completed run is still opened here we send one terminal `run_status`
    and close, so the client isn't left hanging waiting for more.
    """
    origin = websocket.headers.get("origin")
    if not origin or origin not in settings.cors_origins:
        await websocket.close(code=4001, reason="Invalid origin")
        return

    aviary_session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not aviary_session_id:
        await websocket.close(code=4001, reason="Missing session")
        return
    initial_session = await get_fresh_session(aviary_session_id)
    if initial_session is None:
        await websocket.close(code=4001, reason="Invalid or expired session")
        return
    try:
        claims = await validate_token(initial_session.access_token)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    run_id_str = str(run_id)
    pubsub = None

    try:
        async with async_session_factory() as db:
            user = (await db.execute(
                select(User).where(User.external_id == claims.sub)
            )).scalar_one_or_none()
            if not user:
                await websocket.send_json({"type": "error", "message": "User not found"})
                return

            run = await workflow_run_service.get_run(db, run_id)
            if not run or run.workflow_id != workflow_id:
                await websocket.send_json({"type": "error", "message": "Run not found"})
                return

            workflow = await workflow_service.get_workflow(db, workflow_id)
            if not workflow or workflow.owner_id != user.id:
                await websocket.send_json({"type": "error", "message": "Not authorized"})
                return

            if run.status in _TERMINAL_RUN_STATUSES:
                terminal = {"type": "run_status", "status": run.status}
                if run.error:
                    terminal["error"] = run.error
                await websocket.send_json(terminal)
                return

        # Replay anything the worker has already published for this run so a
        # client that connects mid-stream catches up. Subscribe first so no
        # event slips between the LRANGE and the listen loop.
        pubsub = await redis_service.subscribe_workflow_run(run_id_str)
        if pubsub is None:
            return

        for event in await redis_service.get_workflow_run_replay(run_id_str):
            await websocket.send_json(event)

        async for raw_msg in pubsub.listen():
            if raw_msg["type"] != "message":
                continue
            try:
                event = json.loads(raw_msg["data"])
            except json.JSONDecodeError:
                logger.warning("Non-JSON event on run=%s channel", run_id_str)
                continue
            await websocket.send_json(event)
            if (
                event.get("type") == "run_status"
                and event.get("status") in _TERMINAL_RUN_STATUSES
            ):
                return

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("workflow run ws crashed for run=%s", run_id_str)
    finally:
        if pubsub:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe()
                await pubsub.aclose()

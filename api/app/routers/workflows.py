"""Workflow CRUD + deploy/edit/versions + run trigger/cancel/list/WS."""

import contextlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
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
from app.services import redis_service, workflow_run_service, workflow_service

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


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionResponse])
async def list_workflow_versions(
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    versions = await workflow_service.list_workflow_versions(db, workflow.id)
    return [WorkflowVersionResponse.from_orm_version(v) for v in versions]


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
    include_drafts: bool = Query(False),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    workflow: Workflow = Depends(require_workflow_owner()),
    db: AsyncSession = Depends(get_db),
):
    runs, total = await workflow_run_service.list_runs(
        db, workflow.id, include_drafts=include_drafts, offset=offset, limit=limit,
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

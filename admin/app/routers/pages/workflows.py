"""Workflow list, detail, and policy pages."""

import math
import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aviary_shared.db.models import Workflow, Policy
from app.db import get_db
from app.services import supervisor_client
from app.routers.pages._templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/workflows", response_class=HTMLResponse)
async def workflow_list(request: Request, page: int = 1, db: AsyncSession = Depends(get_db)):
    per_page = 50
    offset = (page - 1) * per_page

    total_result = await db.execute(select(func.count()).select_from(Workflow))
    total = total_result.scalar() or 0
    total_pages = max(1, math.ceil(total / per_page))

    result = await db.execute(
        select(Workflow).order_by(Workflow.created_at.desc()).offset(offset).limit(per_page)
    )
    workflows = list(result.scalars().all())

    deployment_map: dict[str, dict] = {}
    for wf in workflows:
        try:
            status_info = await supervisor_client.get_deployment_status(str(wf.id))
            ready = status_info.get("ready_replicas") or 0
            deployment_map[str(wf.id)] = {"state": "active" if ready > 0 else "inactive", "ready": ready}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                deployment_map[str(wf.id)] = {"state": "inactive", "ready": 0}
            else:
                deployment_map[str(wf.id)] = {"state": "unknown", "ready": 0}
        except httpx.HTTPError:
            deployment_map[str(wf.id)] = {"state": "unknown", "ready": 0}

    return templates.TemplateResponse(request, "workflows.html", {
        "workflows": workflows,
        "deployments": deployment_map,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    })


@router.get("/workflows/{workflow_id}", response_class=HTMLResponse)
async def workflow_detail(
    request: Request, workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.policy))
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        return RedirectResponse("/workflows?error=Workflow+not+found", status_code=303)

    try:
        dep_info = await supervisor_client.get_deployment_status(str(workflow.id))
        deployment_status = {
            "active": (dep_info.get("ready_replicas") or 0) > 0,
            "state": "active" if (dep_info.get("ready_replicas") or 0) > 0 else "inactive",
            **dep_info,
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            deployment_status = {"state": "inactive", "active": False, "replicas": 0, "ready_replicas": 0}
        else:
            deployment_status = {"state": "unknown", "active": False, "replicas": 0, "ready_replicas": 0}
    except httpx.HTTPError:
        deployment_status = {"state": "unknown", "active": False, "replicas": 0, "ready_replicas": 0}

    policy_obj = workflow.policy
    policy_rules = policy_obj.policy_rules if policy_obj else {}
    egress_rules = policy_rules.get("allowedEgress", [])

    return templates.TemplateResponse(request, "workflow_detail.html", {
        "workflow": workflow,
        "deployment": deployment_status,
        "policy": policy_rules,
        "policy_obj": policy_obj,
        "egress_rules": egress_rules,
    })


@router.post("/workflows/{workflow_id}/policy")
async def update_workflow_policy(
    request: Request, workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id).options(selectinload(Workflow.policy))
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        return RedirectResponse(f"/workflows/{workflow_id}?error=Not+found", status_code=303)

    form = await request.form()

    if not workflow.policy:
        policy_obj = Policy()
        db.add(policy_obj)
        await db.flush()
        workflow.policy_id = policy_obj.id
        workflow.policy = policy_obj

    policy_obj = workflow.policy
    policy_obj.pod_strategy = form.get("pod_strategy") or policy_obj.pod_strategy
    policy_obj.min_pods = int(form.get("min_pods") or policy_obj.min_pods)
    policy_obj.max_pods = int(form.get("max_pods") or policy_obj.max_pods)

    policy_rules = dict(policy_obj.policy_rules) if policy_obj.policy_rules else {}
    policy_rules["maxMemoryPerSession"] = form.get("max_memory") or "4Gi"
    policy_rules["maxCpuPerSession"] = form.get("max_cpu") or "4"
    policy_rules["maxConcurrentSessions"] = int(form.get("max_concurrent_sessions") or 20)

    names = form.getlist("egress_name[]")
    types = form.getlist("egress_type[]")
    targets = form.getlist("egress_target[]")
    ports_list = form.getlist("egress_ports[]")
    egress_rules = []
    for i in range(len(names)):
        name = names[i].strip()
        target = targets[i].strip() if i < len(targets) else ""
        if not name or not target:
            continue
        rule = {"name": name}
        if i < len(types) and types[i] == "cidr":
            rule["cidr"] = target
        else:
            rule["domain"] = target
        ports_str = ports_list[i].strip() if i < len(ports_list) else ""
        ports = []
        if ports_str:
            for p in ports_str.split(","):
                p = p.strip()
                if p.isdigit():
                    ports.append({"port": int(p), "protocol": "TCP"})
        rule["ports"] = ports
        egress_rules.append(rule)

    policy_rules["allowedEgress"] = egress_rules
    policy_obj.policy_rules = policy_rules
    await db.flush()

    return RedirectResponse(f"/workflows/{workflow_id}?flash=Policy+saved", status_code=303)


@router.post("/workflows/{workflow_id}/delete")
async def delete_workflow(workflow_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        return RedirectResponse("/workflows?error=Not+found", status_code=303)

    try:
        await supervisor_client.delete_agent(str(workflow.id))
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning("Cleanup failed for workflow %s", workflow.id, exc_info=True)
    except httpx.HTTPError:
        pass

    await db.delete(workflow)
    await db.flush()
    return RedirectResponse("/workflows?flash=Workflow+deleted", status_code=303)

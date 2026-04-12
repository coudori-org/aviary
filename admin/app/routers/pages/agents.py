"""Agent list, detail, config, policy, deployment, and delete pages."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from aviary_shared.db.models import Agent
from aviary_shared.naming import agent_namespace
from app.db import get_db
from app.services import agent_lifecycle, supervisor_client
from app.routers.pages._templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def agent_list(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    per_page = 20
    offset = (page - 1) * per_page

    from sqlalchemy import func
    count_result = await db.execute(select(func.count()).select_from(Agent))
    total = count_result.scalar() or 0
    total_pages = max(1, (total + per_page - 1) // per_page)

    result = await db.execute(
        select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(per_page).options(selectinload(Agent.policy))
    )
    agents = list(result.scalars().all())

    deployment_map: dict[str, dict] = {}
    for agent in agents:
        ns = agent_namespace(str(agent.id))
        try:
            status_info = await supervisor_client.get_deployment_status(ns)
            ready = status_info.get("ready_replicas") or 0
            deployment_map[str(agent.id)] = {"state": "active" if ready > 0 else "inactive", "ready": ready}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                deployment_map[str(agent.id)] = {"state": "inactive", "ready": 0}
            else:
                logger.warning("Status fetch failed for agent %s", agent.id, exc_info=True)
                deployment_map[str(agent.id)] = {"state": "unknown", "ready": 0}
        except httpx.HTTPError:
            logger.warning("Status fetch failed for agent %s", agent.id, exc_info=True)
            deployment_map[str(agent.id)] = {"state": "unknown", "ready": 0}

    return templates.TemplateResponse(request, "agents.html", {
        "agents": agents,
        "deployments": deployment_map,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@router.get("/agents/{agent_id}", response_class=HTMLResponse)
async def agent_detail(
    request: Request, agent_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy)))
    agent = result.scalar_one_or_none()
    if not agent:
        return HTMLResponse("<h1>Agent not found</h1>", status_code=404)

    ns = agent_namespace(str(agent.id))
    deployment_status = {"state": "inactive", "active": False, "replicas": 0, "ready_replicas": 0}
    try:
        status_info = await supervisor_client.get_deployment_status(ns)
        replicas = status_info.get("replicas", 0)
        ready = status_info.get("ready_replicas", 0)
        deployment_status = {
            "state": "active" if ready > 0 else "inactive",
            "active": ready > 0,
            "replicas": replicas,
            "ready_replicas": ready,
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning("Status fetch failed for agent %s", agent.id, exc_info=True)
            deployment_status = {"state": "unknown", "active": False, "replicas": 0, "ready_replicas": 0}
    except httpx.HTTPError:
        logger.warning("Status fetch failed for agent %s", agent.id, exc_info=True)
        deployment_status = {"state": "unknown", "active": False, "replicas": 0, "ready_replicas": 0}

    policy_obj = agent.policy
    policy_rules = policy_obj.policy_rules if policy_obj else {}
    egress_rules = policy_rules.get("allowedEgress", [])
    flash = request.query_params.get("flash")
    flash_data = None
    if flash:
        flash_data = {"type": "success", "message": flash}
    error = request.query_params.get("error")
    if error:
        flash_data = {"type": "error", "message": error}

    return templates.TemplateResponse(request, "agent_detail.html", {
        "agent": agent,
        "deployment": deployment_status,
        "policy": policy_rules,
        "policy_obj": policy_obj,
        "egress_rules": egress_rules,
        "flash": flash_data,
    })


@router.post("/agents/{agent_id}/update")
async def update_agent_config(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    instruction: str = Form(...),
    visibility: str = Form("private"),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy)))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    agent.name = name
    agent.description = description or None
    agent.instruction = instruction
    agent.visibility = visibility
    await db.flush()

    return RedirectResponse(f"/agents/{agent_id}?flash=Configuration+saved", status_code=303)


@router.post("/agents/{agent_id}/policy")
async def update_policy(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from aviary_shared.db.models import Policy
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    form = await request.form()

    # Ensure policy entity exists
    if not agent.policy:
        policy_obj = Policy()
        db.add(policy_obj)
        await db.flush()
        agent.policy_id = policy_obj.id
        agent.policy = policy_obj

    policy_obj = agent.policy

    # Parse scaling fields
    policy_obj.pod_strategy = form.get("pod_strategy") or policy_obj.pod_strategy
    policy_obj.min_pods = int(form.get("min_pods") or policy_obj.min_pods)
    policy_obj.max_pods = int(form.get("max_pods") or policy_obj.max_pods)

    # Build policy rules dict
    policy_rules = dict(policy_obj.policy_rules) if policy_obj.policy_rules else {}
    policy_rules["maxMemoryPerSession"] = form.get("max_memory", "4Gi")
    policy_rules["maxCpuPerSession"] = form.get("max_cpu", "4")
    policy_rules["maxConcurrentSessions"] = int(form.get("max_concurrent_sessions") or 20)
    policy_rules["maxTokensPerTurn"] = int(form.get("max_tokens_per_turn") or 100000)
    policy_rules["containerImage"] = form.get("container_image") or "aviary-runtime:latest"
    policy_rules["maxConcurrentSessionsPerPod"] = int(form.get("max_sessions_per_pod") or 10)
    # Parse egress rules
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

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.update_network_policy(ns, policy_rules)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)
            return RedirectResponse(f"/agents/{agent_id}?error=Policy+saved+but+K8s+sync+failed:+{e}", status_code=303)
    except httpx.HTTPError as e:
        logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)
        return RedirectResponse(f"/agents/{agent_id}?error=Policy+saved+but+K8s+sync+failed:+{e}", status_code=303)

    return RedirectResponse(f"/agents/{agent_id}?flash=Policy+saved", status_code=303)


def _flash_error(agent_id, message: str) -> RedirectResponse:
    return RedirectResponse(f"/agents/{agent_id}?error={message}", status_code=303)


@router.post("/agents/{agent_id}/activate")
async def activate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await agent_lifecycle.find_agent_or_none(db, agent_id)
    if not agent:
        return _flash_error(agent_id, "Agent+not+found")
    try:
        await agent_lifecycle.activate(agent)
    except httpx.HTTPError as e:
        return _flash_error(agent_id, f"Activation+failed:+{e}")
    return RedirectResponse(f"/agents/{agent_id}?flash=Agent+activated", status_code=303)


@router.post("/agents/{agent_id}/deactivate")
async def deactivate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await agent_lifecycle.find_agent_or_none(db, agent_id)
    if not agent:
        return _flash_error(agent_id, "Agent+not+found")
    try:
        await agent_lifecycle.deactivate(agent)
    except httpx.HTTPError as e:
        return _flash_error(agent_id, f"Deactivation+failed:+{e}")
    return RedirectResponse(f"/agents/{agent_id}?flash=Agent+deactivated", status_code=303)


@router.post("/agents/{agent_id}/deploy")
async def deploy_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await agent_lifecycle.find_agent_or_none(db, agent_id)
    if not agent:
        return _flash_error(agent_id, "Agent+not+found")
    try:
        await agent_lifecycle.rolling_restart(agent)
    except httpx.HTTPError as e:
        return _flash_error(agent_id, f"Rolling+restart+failed:+{e}")
    return RedirectResponse(f"/agents/{agent_id}?flash=Rolling+restart+triggered", status_code=303)


@router.post("/agents/{agent_id}/delete")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    agent = await agent_lifecycle.find_agent_or_none(db, agent_id)
    if not agent:
        return RedirectResponse("/?error=Agent+not+found", status_code=303)
    try:
        await agent_lifecycle.delete_agent(db, agent)
    except httpx.HTTPError as e:
        return _flash_error(agent_id, f"Delete+failed:+{e}")
    return RedirectResponse("/?flash=Agent+deleted", status_code=303)

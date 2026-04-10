"""Agent list, detail, config, policy, deployment, and delete pages."""

import uuid
import logging

import httpx
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent
from aviary_shared.naming import agent_namespace
from app.db import get_db
from app.services import supervisor_client
from app.routers.pages._templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Agent List ────────────────────────────────────────────────

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
        select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(per_page)
    )
    agents = list(result.scalars().all())

    # Query live deployment status for each agent
    deployment_map: dict[str, dict] = {}
    for agent in agents:
        ns = agent_namespace(str(agent.id))
        try:
            status_info = await supervisor_client.get_deployment_status(ns)
            ready = status_info.get("ready_replicas") or 0
            deployment_map[str(agent.id)] = {"active": ready > 0, "ready": ready}
        except httpx.HTTPError:  # Best-effort: deployment may not exist
            deployment_map[str(agent.id)] = {"active": False, "ready": 0}

    return templates.TemplateResponse(request, "agents.html", {
        "agents": agents,
        "deployments": deployment_map,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


# ── Agent Detail ──────────────────────────────────────────────

@router.get("/agents/{agent_id}", response_class=HTMLResponse)
async def agent_detail(
    request: Request, agent_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return HTMLResponse("<h1>Agent not found</h1>", status_code=404)

    # Query live deployment status from supervisor
    ns = agent_namespace(str(agent.id))
    deployment_status = {"active": False, "replicas": 0, "ready_replicas": 0}
    try:
        status_info = await supervisor_client.get_deployment_status(ns)
        replicas = status_info.get("replicas", 0)
        ready = status_info.get("ready_replicas", 0)
        deployment_status = {
            "active": ready > 0,
            "replicas": replicas,
            "ready_replicas": ready,
        }
    except httpx.HTTPError:  # Best-effort: deployment may not exist
        pass

    policy = agent.policy or {}
    egress_rules = policy.get("allowedEgress", [])
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
        "policy": policy,
        "egress_rules": egress_rules,
        "flash": flash_data,
    })


# ── Agent Config Update ──────────────────────────────────────

@router.post("/agents/{agent_id}/update")
async def update_agent_config(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    description: str = Form(""),
    instruction: str = Form(...),
    visibility: str = Form("private"),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    agent.name = name
    agent.description = description or None
    agent.instruction = instruction
    agent.visibility = visibility
    await db.flush()

    return RedirectResponse(f"/agents/{agent_id}?flash=Configuration+saved", status_code=303)


# ── Policy Update ─────────────────────────────────────────────

@router.post("/agents/{agent_id}/policy")
async def update_policy(
    agent_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    form = await request.form()

    # Parse scaling fields
    agent.pod_strategy = form.get("pod_strategy", agent.pod_strategy)
    agent.min_pods = int(form.get("min_pods", agent.min_pods))
    agent.max_pods = int(form.get("max_pods", agent.max_pods))

    # Build policy dict
    policy = dict(agent.policy) if agent.policy else {}
    policy["maxMemoryPerSession"] = form.get("max_memory", "4Gi")
    policy["maxCpuPerSession"] = form.get("max_cpu", "4")
    policy["maxConcurrentSessions"] = int(form.get("max_concurrent_sessions", 20))
    # TODO: enforce in API server by clamping max_tokens before forwarding to supervisor
    policy["maxTokensPerTurn"] = int(form.get("max_tokens_per_turn", 100000))
    policy["containerImage"] = form.get("container_image", "aviary-runtime:latest")
    policy["maxConcurrentSessionsPerPod"] = int(form.get("max_sessions_per_pod", 10))
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
        # Parse ports
        ports_str = ports_list[i].strip() if i < len(ports_list) else ""
        ports = []
        if ports_str:
            for p in ports_str.split(","):
                p = p.strip()
                if p.isdigit():
                    ports.append({"port": int(p), "protocol": "TCP"})
        rule["ports"] = ports
        egress_rules.append(rule)

    policy["allowedEgress"] = egress_rules
    agent.policy = policy
    await db.flush()

    # Sync K8s NetworkPolicy
    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.update_network_policy(ns, policy)
    except httpx.HTTPError:
        logger.warning("NetworkPolicy update failed for agent %s", agent.id, exc_info=True)

    return RedirectResponse(f"/agents/{agent_id}?flash=Policy+saved", status_code=303)


# ── Deployment Actions ────────────────────────────────────────

@router.post("/agents/{agent_id}/activate")
async def activate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    ns = agent_namespace(str(agent.id))
    try:
        # Ensure namespace exists
        try:
            await supervisor_client.create_namespace(
                agent_id=str(agent.id), owner_id=str(agent.owner_id),
                policy=agent.policy or {},
            )
        except httpx.HTTPError:  # Best-effort: namespace may already exist
            pass

        await supervisor_client.ensure_deployment(
            namespace=ns, agent_id=str(agent.id), owner_id=str(agent.owner_id),
            policy=agent.policy or {},
            min_pods=agent.min_pods, max_pods=agent.max_pods,
        )
        return RedirectResponse(f"/agents/{agent_id}?flash=Agent+activated", status_code=303)
    except httpx.HTTPError as e:
        return RedirectResponse(f"/agents/{agent_id}?error=Activation+failed:+{e}", status_code=303)


@router.post("/agents/{agent_id}/deactivate")
async def deactivate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.scale_to_zero(ns)
    except httpx.HTTPError:  # Best-effort: scale-down failure is non-critical
        pass
    return RedirectResponse(f"/agents/{agent_id}?flash=Agent+deactivated", status_code=303)


@router.post("/agents/{agent_id}/deploy")
async def deploy_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.rolling_restart(ns)
    except httpx.HTTPError:  # Best-effort: restart failure is non-critical for UI redirect
        pass
    return RedirectResponse(f"/agents/{agent_id}?flash=Rolling+restart+triggered", status_code=303)


@router.post("/agents/{agent_id}/delete")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from aviary_shared.db.models import Session as SessionModel

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse("/?error=Agent+not+found", status_code=303)

    # Clean up K8s resources
    ns = agent_namespace(str(agent.id))
    try:
        await supervisor_client.delete_deployment(ns)
    except httpx.HTTPError:  # Best-effort: K8s resources may already be gone
        pass
    try:
        await supervisor_client.delete_namespace(str(agent.id))
    except httpx.HTTPError:  # Best-effort: namespace may already be gone
        pass

    # Delete all sessions for this agent, then the agent itself
    await db.execute(
        select(SessionModel).where(SessionModel.agent_id == agent.id).execution_options(synchronize_session="fetch")
    )
    from sqlalchemy import delete
    await db.execute(delete(SessionModel).where(SessionModel.agent_id == agent.id))
    await db.delete(agent)
    await db.flush()
    return RedirectResponse("/?flash=Agent+deleted", status_code=303)

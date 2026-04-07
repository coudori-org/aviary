"""HTML pages — serves the admin web UI via Jinja2 templates."""

import uuid
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent, McpServer, McpTool, McpToolAcl, Team, TeamMember, User
from app.db import get_db
from app.services import supervisor_client

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
        ns = f"agent-{agent.id}"
        try:
            status_info = await supervisor_client.get_deployment_status(ns)
            ready = status_info.get("ready_replicas") or 0
            deployment_map[str(agent.id)] = {"active": ready > 0, "ready": ready}
        except Exception:
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
    ns = f"agent-{agent.id}"
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
    except Exception:
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
    ns = f"agent-{agent.id}"
    try:
        await supervisor_client.update_network_policy(ns, policy)
    except Exception:
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

    ns = f"agent-{agent.id}"
    try:
        # Ensure namespace exists
        try:
            await supervisor_client.create_namespace(
                agent_id=str(agent.id), owner_id=str(agent.owner_id),
                policy=agent.policy or {},
            )
        except Exception:
            pass  # Already exists

        await supervisor_client.ensure_deployment(
            namespace=ns, agent_id=str(agent.id), owner_id=str(agent.owner_id),
            policy=agent.policy or {},
            min_pods=agent.min_pods, max_pods=agent.max_pods,
        )
        return RedirectResponse(f"/agents/{agent_id}?flash=Agent+activated", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/agents/{agent_id}?error=Activation+failed:+{e}", status_code=303)


@router.post("/agents/{agent_id}/deactivate")
async def deactivate_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    ns = f"agent-{agent.id}"
    try:
        await supervisor_client.scale_to_zero(ns)
    except Exception:
        pass
    return RedirectResponse(f"/agents/{agent_id}?flash=Agent+deactivated", status_code=303)


@router.post("/agents/{agent_id}/deploy")
async def deploy_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse(f"/agents/{agent_id}?error=Agent+not+found", status_code=303)

    ns = f"agent-{agent.id}"
    try:
        await supervisor_client.rolling_restart(ns)
    except Exception:
        pass
    return RedirectResponse(f"/agents/{agent_id}?flash=Rolling+restart+triggered", status_code=303)


# ── User Pages ──────────────────────────────────���─────────────


@router.get("/users", response_class=HTMLResponse)
async def user_list(request: Request, db: AsyncSession = Depends(get_db)):
    from app.routers.users import _sync_keycloak_users
    await _sync_keycloak_users(db)

    result = await db.execute(select(User).order_by(User.created_at.desc()))
    all_users = list(result.scalars().all())

    user_data = []
    for u in all_users:
        result = await db.execute(
            select(Team.name)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == u.id)
        )
        teams = list(result.scalars().all())
        user_data.append({
            "id": str(u.id),
            "external_id": u.external_id,
            "email": u.email,
            "display_name": u.display_name,
            "is_platform_admin": u.is_platform_admin,
            "teams": teams,
            "created_at": u.created_at.isoformat(),
        })

    return templates.TemplateResponse(request, "users.html", {"users": user_data})


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: str, db: AsyncSession = Depends(get_db)):
    from app.routers.users import _vault_list_keys, _vault_get_key

    u_uuid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == u_uuid))
    user = result.scalar_one_or_none()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    result = await db.execute(
        select(Team.name)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
    )
    teams = list(result.scalars().all())

    user_data = {
        "id": str(user.id),
        "external_id": user.external_id,
        "email": user.email,
        "display_name": user.display_name,
        "is_platform_admin": user.is_platform_admin,
        "teams": teams,
        "created_at": user.created_at.isoformat(),
    }

    # Fetch Vault credentials
    credentials = []
    try:
        keys = await _vault_list_keys(user.external_id)
        for key in keys:
            key = key.rstrip("/")
            data = await _vault_get_key(user.external_id, key)
            if data:
                token = data.get("value", "")
                masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
                credentials.append({"key": key, "value": masked})
    except Exception:
        pass  # Vault may not be reachable

    return templates.TemplateResponse(request, "user_detail.html", {
        "user": user_data,
        "credentials": credentials,
    })


# ── MCP Server Pages ─────────────────────────────���────────────


@router.get("/mcp", response_class=HTMLResponse)
async def mcp_server_list(request: Request, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func as sa_func

    result = await db.execute(
        select(McpServer).order_by(McpServer.created_at.desc())
    )
    servers = list(result.scalars().all())

    server_data = []
    for srv in servers:
        count_result = await db.execute(
            select(sa_func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
        )
        tool_count = count_result.scalar() or 0
        server_data.append({
            "id": str(srv.id),
            "name": srv.name,
            "description": srv.description,
            "transport_type": srv.transport_type,
            "status": srv.status,
            "tool_count": tool_count,
            "last_discovered_at": srv.last_discovered_at.isoformat() if srv.last_discovered_at else None,
        })

    return templates.TemplateResponse(request, "mcp_servers.html", {
        "servers": server_data,
    })


@router.get("/mcp/{server_id}", response_class=HTMLResponse)
async def mcp_server_detail(
    request: Request, server_id: str, db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func as sa_func

    srv_uuid = uuid.UUID(server_id)
    result = await db.execute(select(McpServer).where(McpServer.id == srv_uuid))
    srv = result.scalar_one_or_none()
    if not srv:
        return HTMLResponse("<h1>Server not found</h1>", status_code=404)

    count_result = await db.execute(
        select(sa_func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
    )
    tool_count = count_result.scalar() or 0

    server_data = {
        "id": str(srv.id),
        "name": srv.name,
        "description": srv.description,
        "transport_type": srv.transport_type,
        "status": srv.status,
        "tool_count": tool_count,
        "last_discovered_at": srv.last_discovered_at.isoformat() if srv.last_discovered_at else None,
    }

    result = await db.execute(
        select(McpTool).where(McpTool.server_id == srv.id).order_by(McpTool.name)
    )
    tools = [
        {"id": str(t.id), "name": t.name, "description": t.description}
        for t in result.scalars().all()
    ]

    result = await db.execute(
        select(McpToolAcl).where(McpToolAcl.server_id == srv.id).order_by(McpToolAcl.created_at.desc())
    )
    acl_rules = [
        {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "team_id": str(r.team_id) if r.team_id else None,
            "tool_id": str(r.tool_id) if r.tool_id else None,
            "permission": r.permission,
        }
        for r in result.scalars().all()
    ]

    return templates.TemplateResponse(request, "mcp_server_detail.html", {
        "server": server_data,
        "tools": tools,
        "acl_rules": acl_rules,
    })


@router.post("/agents/{agent_id}/delete")
async def delete_agent(agent_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from aviary_shared.db.models import Session as SessionModel

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        return RedirectResponse("/?error=Agent+not+found", status_code=303)

    # Clean up K8s resources
    ns = f"agent-{agent.id}"
    try:
        await supervisor_client.delete_deployment(ns)
    except Exception:
        pass
    try:
        await supervisor_client.delete_namespace(str(agent.id))
    except Exception:
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

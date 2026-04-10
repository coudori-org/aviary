"""MCP server list and detail pages."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool, McpToolAcl
from app.db import get_db
from app.routers.pages._templates import templates

router = APIRouter()


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

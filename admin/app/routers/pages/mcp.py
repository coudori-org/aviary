"""MCP server list and detail pages."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool
from app.db import get_db
from app.routers.pages._templates import templates

router = APIRouter()


@router.get("/mcp", response_class=HTMLResponse)
async def mcp_server_list(request: Request, db: AsyncSession = Depends(get_db)):
    servers = list((await db.execute(
        select(McpServer).order_by(McpServer.created_at.desc())
    )).scalars().all())

    server_data = []
    for srv in servers:
        tool_count = (await db.execute(
            select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
        )).scalar() or 0
        server_data.append({
            "id": str(srv.id),
            "name": srv.name,
            "description": srv.description,
            "transport_type": srv.transport_type,
            "status": srv.status,
            "tool_count": tool_count,
            "last_discovered_at": srv.last_discovered_at.isoformat() if srv.last_discovered_at else None,
        })

    return templates.TemplateResponse(request, "mcp_servers.html", {"servers": server_data})


@router.get("/mcp/{server_id}", response_class=HTMLResponse)
async def mcp_server_detail(
    request: Request, server_id: str, db: AsyncSession = Depends(get_db),
):
    srv_uuid = uuid.UUID(server_id)
    srv = (await db.execute(select(McpServer).where(McpServer.id == srv_uuid))).scalar_one_or_none()
    if not srv:
        return HTMLResponse("<h1>Server not found</h1>", status_code=404)

    tool_count = (await db.execute(
        select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
    )).scalar() or 0

    tools = [
        {"id": str(t.id), "name": t.name, "description": t.description}
        for t in (await db.execute(
            select(McpTool).where(McpTool.server_id == srv.id).order_by(McpTool.name)
        )).scalars().all()
    ]

    return templates.TemplateResponse(request, "mcp_server_detail.html", {
        "server": {
            "id": str(srv.id),
            "name": srv.name,
            "description": srv.description,
            "transport_type": srv.transport_type,
            "status": srv.status,
            "tool_count": tool_count,
            "last_discovered_at": srv.last_discovered_at.isoformat() if srv.last_discovered_at else None,
        },
        "tools": tools,
    })

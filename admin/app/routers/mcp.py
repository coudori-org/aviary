"""MCP server catalog management — admin only (no auth).

ACL was removed alongside the broader rollback; every registered server is
globally available to any agent that binds its tools."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool
from aviary_shared.mcp_tools import upsert_tools
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class McpServerCreate(BaseModel):
    name: str
    description: str | None = None
    transport_type: str = "streamable_http"
    connection_config: dict = {}
    tags: list[str] = []


class McpServerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    transport_type: str | None = None
    connection_config: dict | None = None
    tags: list[str] | None = None
    status: str | None = None


class McpServerResponse(BaseModel):
    id: str
    name: str
    description: str | None
    transport_type: str
    connection_config: dict
    tags: list
    status: str
    last_discovered_at: str | None
    tool_count: int
    created_at: str
    updated_at: str


class McpToolResponse(BaseModel):
    id: str
    server_id: str
    server_name: str
    name: str
    description: str | None
    input_schema: dict
    created_at: str


async def _server_response(db: AsyncSession, srv: McpServer) -> McpServerResponse:
    tool_count = (await db.execute(
        select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
    )).scalar() or 0
    return McpServerResponse(
        id=str(srv.id),
        name=srv.name,
        description=srv.description,
        transport_type=srv.transport_type,
        connection_config=srv.connection_config,
        tags=srv.tags,
        status=srv.status,
        last_discovered_at=srv.last_discovered_at.isoformat() if srv.last_discovered_at else None,
        tool_count=tool_count,
        created_at=srv.created_at.isoformat(),
        updated_at=srv.updated_at.isoformat(),
    )


@router.get("/servers", response_model=list[McpServerResponse])
async def list_servers(db: AsyncSession = Depends(get_db)):
    servers = (await db.execute(
        select(McpServer).order_by(McpServer.created_at.desc())
    )).scalars().all()
    return [await _server_response(db, srv) for srv in servers]


@router.post("/servers", response_model=McpServerResponse, status_code=201)
async def create_server(body: McpServerCreate, db: AsyncSession = Depends(get_db)):
    srv = McpServer(
        name=body.name,
        description=body.description,
        transport_type=body.transport_type,
        connection_config=body.connection_config,
        tags=body.tags,
    )
    db.add(srv)
    await db.flush()
    await db.refresh(srv)
    return await _server_response(db, srv)


@router.put("/servers/{server_id}", response_model=McpServerResponse)
async def update_server(
    server_id: uuid.UUID, body: McpServerUpdate, db: AsyncSession = Depends(get_db),
):
    srv = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    for field in ("name", "description", "transport_type", "connection_config", "tags", "status"):
        value = getattr(body, field)
        if value is not None:
            setattr(srv, field, value)

    await db.flush()
    await db.refresh(srv)
    return await _server_response(db, srv)


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    srv = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")
    await db.delete(srv)
    await db.flush()
    return None


@router.post("/servers/{server_id}/discover")
async def discover_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Connect to an MCP server via MCP SDK and discover its tools."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    srv = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    url = srv.connection_config.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Server has no URL in connection_config")

    headers = srv.connection_config.get("headers", {})

    try:
        async with streamablehttp_client(url=url, headers=headers) as (
            read_stream, write_stream, _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
    except Exception as e:
        srv.status = "error"
        await db.flush()
        raise HTTPException(status_code=502, detail=f"Failed to connect to MCP server: {e}") from e

    raw_tools = [
        {"name": t.name, "description": t.description or "",
         "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {}}
        for t in tools_result.tools
    ]
    discovered, removed = await upsert_tools(db, srv, raw_tools)
    return {"discovered": discovered, "removed": removed}


@router.get("/servers/{server_id}/tools", response_model=list[McpToolResponse])
async def list_server_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    srv = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    tools = (await db.execute(
        select(McpTool).where(McpTool.server_id == server_id).order_by(McpTool.name)
    )).scalars().all()

    return [
        McpToolResponse(
            id=str(t.id),
            server_id=str(t.server_id),
            server_name=srv.name,
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
            created_at=t.created_at.isoformat(),
        )
        for t in tools
    ]

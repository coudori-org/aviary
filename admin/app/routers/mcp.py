"""MCP server catalog and ACL management — admin only (no auth)."""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool, McpToolAcl
from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────


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


class McpAclCreate(BaseModel):
    server_id: str
    tool_id: str | None = None
    user_id: str | None = None
    team_id: str | None = None
    permission: str = "use"


class McpAclResponse(BaseModel):
    id: str
    server_id: str
    tool_id: str | None
    user_id: str | None
    team_id: str | None
    permission: str
    created_at: str


# ── Server CRUD ──────────────────────────────────────────────


@router.get("/servers", response_model=list[McpServerResponse])
async def list_servers(db: AsyncSession = Depends(get_db)):
    """List all registered MCP servers with tool counts."""
    result = await db.execute(
        select(McpServer).order_by(McpServer.created_at.desc())
    )
    servers = result.scalars().all()

    responses = []
    for srv in servers:
        count_result = await db.execute(
            select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
        )
        tool_count = count_result.scalar() or 0

        responses.append(McpServerResponse(
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
        ))

    return responses


@router.post("/servers", response_model=McpServerResponse, status_code=201)
async def create_server(body: McpServerCreate, db: AsyncSession = Depends(get_db)):
    """Register a new MCP server in the catalog."""
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

    return McpServerResponse(
        id=str(srv.id),
        name=srv.name,
        description=srv.description,
        transport_type=srv.transport_type,
        connection_config=srv.connection_config,
        tags=srv.tags,
        status=srv.status,
        last_discovered_at=None,
        tool_count=0,
        created_at=srv.created_at.isoformat(),
        updated_at=srv.updated_at.isoformat(),
    )


@router.put("/servers/{server_id}", response_model=McpServerResponse)
async def update_server(
    server_id: uuid.UUID, body: McpServerUpdate, db: AsyncSession = Depends(get_db)
):
    """Update an MCP server's configuration."""
    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    srv = result.scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    if body.name is not None:
        srv.name = body.name
    if body.description is not None:
        srv.description = body.description
    if body.transport_type is not None:
        srv.transport_type = body.transport_type
    if body.connection_config is not None:
        srv.connection_config = body.connection_config
    if body.tags is not None:
        srv.tags = body.tags
    if body.status is not None:
        srv.status = body.status

    await db.flush()
    await db.refresh(srv)

    count_result = await db.execute(
        select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
    )
    tool_count = count_result.scalar() or 0

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


@router.delete("/servers/{server_id}", status_code=204)
async def delete_server(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete an MCP server and all its tools, bindings, and ACL rules (cascaded)."""
    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    srv = result.scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    await db.delete(srv)
    await db.flush()
    return None


# ── Tool Discovery ───────────────────────────────────────────


@router.post("/servers/{server_id}/discover")
async def discover_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Connect to an MCP server via MCP SDK and discover its tools."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    srv = result.scalar_one_or_none()
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
    except Exception as e:  # MCP SDK can raise various errors (transport, protocol, timeout)
        srv.status = "error"
        await db.flush()
        raise HTTPException(status_code=502, detail=f"Failed to connect to MCP server: {e}")

    raw_tools = [
        {"name": t.name, "description": t.description or "",
         "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {}}
        for t in tools_result.tools
    ]

    # Upsert tools
    existing_result = await db.execute(
        select(McpTool).where(McpTool.server_id == server_id)
    )
    existing = {t.name: t for t in existing_result.scalars().all()}

    discovered_names = set()
    for raw in raw_tools:
        name = raw["name"]
        discovered_names.add(name)
        if name in existing:
            existing[name].description = raw.get("description", "")
            existing[name].input_schema = raw.get("inputSchema", {})
        else:
            db.add(McpTool(
                server_id=server_id,
                name=name,
                description=raw.get("description", ""),
                input_schema=raw.get("inputSchema", {}),
            ))

    for name in set(existing.keys()) - discovered_names:
        await db.delete(existing[name])

    srv.last_discovered_at = datetime.now(timezone.utc)
    srv.status = "active"
    await db.flush()

    return {"discovered": len(raw_tools), "removed": len(set(existing.keys()) - discovered_names)}


@router.get("/servers/{server_id}/tools", response_model=list[McpToolResponse])
async def list_server_tools(server_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """List all discovered tools for a server."""
    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    srv = result.scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="Server not found")

    result = await db.execute(
        select(McpTool).where(McpTool.server_id == server_id).order_by(McpTool.name)
    )
    tools = result.scalars().all()

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


# ── ACL Management ───────────────────────────────────────────


@router.get("/acl", response_model=list[McpAclResponse])
async def list_acl(
    server_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List ACL rules, optionally filtered by server."""
    query = select(McpToolAcl).order_by(McpToolAcl.created_at.desc())
    if server_id:
        query = query.where(McpToolAcl.server_id == server_id)

    result = await db.execute(query)
    rules = result.scalars().all()

    return [
        McpAclResponse(
            id=str(r.id),
            server_id=str(r.server_id),
            tool_id=str(r.tool_id) if r.tool_id else None,
            user_id=str(r.user_id) if r.user_id else None,
            team_id=str(r.team_id) if r.team_id else None,
            permission=r.permission,
            created_at=r.created_at.isoformat(),
        )
        for r in rules
    ]


@router.post("/acl", response_model=McpAclResponse, status_code=201)
async def create_acl(body: McpAclCreate, db: AsyncSession = Depends(get_db)):
    """Create an ACL rule."""
    if not body.user_id and not body.team_id:
        raise HTTPException(status_code=400, detail="Either user_id or team_id is required")
    if body.user_id and body.team_id:
        raise HTTPException(status_code=400, detail="Cannot set both user_id and team_id")

    rule = McpToolAcl(
        server_id=uuid.UUID(body.server_id),
        tool_id=uuid.UUID(body.tool_id) if body.tool_id else None,
        user_id=uuid.UUID(body.user_id) if body.user_id else None,
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        permission=body.permission,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)

    return McpAclResponse(
        id=str(rule.id),
        server_id=str(rule.server_id),
        tool_id=str(rule.tool_id) if rule.tool_id else None,
        user_id=str(rule.user_id) if rule.user_id else None,
        team_id=str(rule.team_id) if rule.team_id else None,
        permission=rule.permission,
        created_at=rule.created_at.isoformat(),
    )


@router.delete("/acl/{acl_id}", status_code=204)
async def delete_acl(acl_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete an ACL rule."""
    result = await db.execute(select(McpToolAcl).where(McpToolAcl.id == acl_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="ACL rule not found")

    await db.delete(rule)
    await db.flush()
    return None

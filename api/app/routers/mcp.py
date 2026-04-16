"""MCP tool catalog and agent-tool binding endpoints.

ACL has been removed alongside the broader rollback; any registered MCP
server is listed and bindable. Access control will return under RBAC."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from aviary_shared.db.models import (
    Agent,
    McpAgentToolBinding,
    McpServer,
    McpTool,
    User,
)
from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.schemas.mcp import (
    McpServerResponse,
    McpToolBindingResponse,
    McpToolBindRequest,
    McpToolResponse,
)

router = APIRouter()

TOOL_NAME_SEPARATOR = "__"


@router.get("/servers", response_model=list[McpServerResponse])
async def list_servers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    servers = (await db.execute(
        select(McpServer).where(McpServer.status == "active").order_by(McpServer.name)
    )).scalars().all()

    responses: list[McpServerResponse] = []
    for srv in servers:
        count = (await db.execute(
            select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
        )).scalar() or 0
        responses.append(McpServerResponse(
            id=str(srv.id),
            name=srv.name,
            description=srv.description,
            tags=srv.tags or [],
            tool_count=count,
        ))
    return responses


@router.get("/servers/{server_id}/tools", response_model=list[McpToolResponse])
async def list_server_tools(
    server_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
            input_schema=t.input_schema or {},
            qualified_name=f"{srv.name}{TOOL_NAME_SEPARATOR}{t.name}",
        )
        for t in tools
    ]


@router.get("/tools/search", response_model=list[McpToolResponse])
async def search_tools(
    q: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pattern = f"%{q}%"
    tools = (await db.execute(
        select(McpTool)
        .join(McpServer)
        .where(
            McpServer.status == "active",
            or_(McpTool.name.ilike(pattern), McpTool.description.ilike(pattern)),
        )
        .options(joinedload(McpTool.server))
        .order_by(McpTool.name)
        .limit(50)
    )).scalars().unique().all()

    return [
        McpToolResponse(
            id=str(t.id),
            server_id=str(t.server_id),
            server_name=t.server.name,
            name=t.name,
            description=t.description,
            input_schema=t.input_schema or {},
            qualified_name=f"{t.server.name}{TOOL_NAME_SEPARATOR}{t.name}",
        )
        for t in tools
    ]


@router.get("/agents/{agent_id}/tools", response_model=list[McpToolBindingResponse])
async def list_agent_tools(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this agent")

    bindings = (await db.execute(
        select(McpAgentToolBinding)
        .where(McpAgentToolBinding.agent_id == agent_id)
        .options(joinedload(McpAgentToolBinding.tool).joinedload(McpTool.server))
    )).scalars().unique().all()

    return [
        McpToolBindingResponse(
            id=str(b.id),
            agent_id=str(b.agent_id),
            tool=McpToolResponse(
                id=str(b.tool.id),
                server_id=str(b.tool.server_id),
                server_name=b.tool.server.name,
                name=b.tool.name,
                description=b.tool.description,
                input_schema=b.tool.input_schema or {},
                qualified_name=f"{b.tool.server.name}{TOOL_NAME_SEPARATOR}{b.tool.name}",
            ),
        )
        for b in bindings
    ]


@router.put("/agents/{agent_id}/tools", response_model=list[McpToolBindingResponse])
async def set_agent_tools(
    agent_id: uuid.UUID,
    body: McpToolBindRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this agent")

    tool_uuids = [uuid.UUID(tid) for tid in body.tool_ids]
    if tool_uuids:
        tools = {
            t.id: t for t in (await db.execute(
                select(McpTool).where(McpTool.id.in_(tool_uuids))
            )).scalars().all()
        }
        for tid in tool_uuids:
            if tid not in tools:
                raise HTTPException(status_code=400, detail=f"Tool not found: {tid}")

    await db.execute(
        delete(McpAgentToolBinding).where(McpAgentToolBinding.agent_id == agent_id)
    )
    for tid in tool_uuids:
        db.add(McpAgentToolBinding(agent_id=agent_id, tool_id=tid))
    await db.flush()

    return await list_agent_tools(agent_id, user, db)


@router.delete("/agents/{agent_id}/tools/{tool_id}", status_code=204)
async def unbind_tool(
    agent_id: uuid.UUID,
    tool_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = (await db.execute(select(Agent).where(Agent.id == agent_id))).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this agent")

    binding = (await db.execute(
        select(McpAgentToolBinding).where(
            McpAgentToolBinding.agent_id == agent_id,
            McpAgentToolBinding.tool_id == tool_id,
        )
    )).scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")

    await db.delete(binding)
    await db.flush()
    return None

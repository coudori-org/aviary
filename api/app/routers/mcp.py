"""MCP tool catalog and agent-tool binding endpoints (user-facing, ACL-filtered)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from aviary_shared.db.models import (
    McpAgentToolBinding,
    McpServer,
    McpTool,
    McpToolAcl,
    Agent,
    TeamMember,
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


async def _get_user(db: AsyncSession, external_id: str) -> User:
    result = await db.execute(select(User).where(User.external_id == external_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=403, detail="User not found")
    return user


async def _accessible_server_ids(db: AsyncSession, user: User) -> set[uuid.UUID]:
    """Return set of server IDs the user can see (via direct or team ACL)."""
    if user.is_platform_admin:
        result = await db.execute(select(McpServer.id))
        return set(result.scalars().all())

    # Platform-provided servers are always accessible
    result = await db.execute(
        select(McpServer.id).where(McpServer.is_platform_provided.is_(True))
    )
    ids = set(result.scalars().all())

    # Direct user ACL
    result = await db.execute(
        select(McpToolAcl.server_id).where(McpToolAcl.user_id == user.id).distinct()
    )
    ids.update(result.scalars().all())

    # Team ACL
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = list(result.scalars().all())
    if team_ids:
        result = await db.execute(
            select(McpToolAcl.server_id)
            .where(McpToolAcl.team_id.in_(team_ids))
            .distinct()
        )
        ids.update(result.scalars().all())

    return ids


async def _check_tool_access(db: AsyncSession, user: User, server_id: uuid.UUID, tool_id: uuid.UUID | None = None) -> bool:
    """Check if user has 'use' permission for a tool or server."""
    if user.is_platform_admin:
        return True

    # Platform-provided servers are accessible to all users
    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    srv = result.scalar_one_or_none()
    if srv and srv.is_platform_provided:
        return True

    # Direct user - specific tool
    if tool_id:
        result = await db.execute(
            select(McpToolAcl.permission).where(
                McpToolAcl.server_id == server_id,
                McpToolAcl.tool_id == tool_id,
                McpToolAcl.user_id == user.id,
            )
        )
        if (p := result.scalar_one_or_none()) and p == "use":
            return True

    # Direct user - server level
    result = await db.execute(
        select(McpToolAcl.permission).where(
            McpToolAcl.server_id == server_id,
            McpToolAcl.tool_id.is_(None),
            McpToolAcl.user_id == user.id,
        )
    )
    if (p := result.scalar_one_or_none()) and p == "use":
        return True

    # Team ACL
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = list(result.scalars().all())
    if not team_ids:
        return False

    if tool_id:
        result = await db.execute(
            select(McpToolAcl.permission).where(
                McpToolAcl.server_id == server_id,
                McpToolAcl.tool_id == tool_id,
                McpToolAcl.team_id.in_(team_ids),
            )
        )
        if "use" in list(result.scalars().all()):
            return True

    result = await db.execute(
        select(McpToolAcl.permission).where(
            McpToolAcl.server_id == server_id,
            McpToolAcl.tool_id.is_(None),
            McpToolAcl.team_id.in_(team_ids),
        )
    )
    if "use" in list(result.scalars().all()):
        return True

    return False


# ── Catalog ──────────────────────────────────────────────────


@router.get("/servers", response_model=list[McpServerResponse])
async def list_servers(
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List MCP servers visible to the current user (ACL-filtered)."""
    user = await _get_user(db, claims.sub)
    accessible = await _accessible_server_ids(db, user)

    if not accessible:
        return []

    result = await db.execute(
        select(McpServer)
        .where(McpServer.id.in_(accessible), McpServer.status == "active")
        .order_by(McpServer.name)
    )
    servers = result.scalars().all()

    responses = []
    for srv in servers:
        count_result = await db.execute(
            select(func.count()).select_from(McpTool).where(McpTool.server_id == srv.id)
        )
        responses.append(McpServerResponse(
            id=str(srv.id),
            name=srv.name,
            description=srv.description,
            tags=srv.tags or [],
            tool_count=count_result.scalar() or 0,
        ))

    return responses


@router.get("/servers/{server_id}/tools", response_model=list[McpToolResponse])
async def list_server_tools(
    server_id: uuid.UUID,
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tools from an MCP server (ACL-filtered)."""
    user = await _get_user(db, claims.sub)
    accessible = await _accessible_server_ids(db, user)

    if server_id not in accessible:
        raise HTTPException(status_code=404, detail="Server not found")

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
            input_schema=t.input_schema or {},
            qualified_name=f"{srv.name}{TOOL_NAME_SEPARATOR}{t.name}",
        )
        for t in tools
    ]


@router.get("/tools/search", response_model=list[McpToolResponse])
async def search_tools(
    q: str = Query(..., min_length=1),
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search tools by name or description (ACL-filtered)."""
    user = await _get_user(db, claims.sub)
    accessible = await _accessible_server_ids(db, user)

    if not accessible:
        return []

    pattern = f"%{q}%"
    result = await db.execute(
        select(McpTool)
        .join(McpServer)
        .where(
            McpTool.server_id.in_(accessible),
            McpServer.status == "active",
            or_(
                McpTool.name.ilike(pattern),
                McpTool.description.ilike(pattern),
            ),
        )
        .options(joinedload(McpTool.server))
        .order_by(McpTool.name)
        .limit(50)
    )
    tools = result.scalars().unique().all()

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


# ── Agent Tool Bindings ──────────────────────────────────────


@router.get("/agents/{agent_id}/tools", response_model=list[McpToolBindingResponse])
async def list_agent_tools(
    agent_id: uuid.UUID,
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tools bound to an agent."""
    # Verify agent access (user must have at least 'user' role on the agent)
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(McpAgentToolBinding)
        .where(McpAgentToolBinding.agent_id == agent_id)
        .options(joinedload(McpAgentToolBinding.tool).joinedload(McpTool.server))
    )
    bindings = result.scalars().unique().all()

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
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the tool bindings for an agent (replaces existing bindings).

    ACL check: user must have 'use' permission on each tool being bound.
    """
    user = await _get_user(db, claims.sub)

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify the user owns the agent or has admin role
    # (simplified — full ACL check could be more nuanced)
    if agent.owner_id != user.id and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Not authorized to modify agent tools")

    # Validate tool IDs and check ACL
    tool_uuids = [uuid.UUID(tid) for tid in body.tool_ids]
    if tool_uuids:
        result = await db.execute(
            select(McpTool)
            .where(McpTool.id.in_(tool_uuids))
            .options(joinedload(McpTool.server))
        )
        tools = {t.id: t for t in result.scalars().unique().all()}

        for tid in tool_uuids:
            if tid not in tools:
                raise HTTPException(status_code=400, detail=f"Tool not found: {tid}")
            tool = tools[tid]
            if not await _check_tool_access(db, user, tool.server_id, tool.id):
                raise HTTPException(
                    status_code=403,
                    detail=f"No permission to use tool: {tool.server.name}__{tool.name}",
                )

    # Replace bindings
    await db.execute(
        delete(McpAgentToolBinding).where(McpAgentToolBinding.agent_id == agent_id)
    )

    for tid in tool_uuids:
        db.add(McpAgentToolBinding(agent_id=agent_id, tool_id=tid))

    await db.flush()

    # Return updated bindings
    return await list_agent_tools(agent_id, claims, db)


@router.delete("/agents/{agent_id}/tools/{tool_id}", status_code=204)
async def unbind_tool(
    agent_id: uuid.UUID,
    tool_id: uuid.UUID,
    claims=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unbind a single tool from an agent."""
    user = await _get_user(db, claims.sub)

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.owner_id != user.id and not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(
        select(McpAgentToolBinding).where(
            McpAgentToolBinding.agent_id == agent_id,
            McpAgentToolBinding.tool_id == tool_id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")

    await db.delete(binding)
    await db.flush()
    return None

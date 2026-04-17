"""MCP catalog + agent-tool binding endpoints — thin relay over LiteLLM.

All visibility decisions are LiteLLM's. This router opens an MCP session
to ``/mcp`` with the caller's OIDC JWT and relays whatever LiteLLM
returns. Aviary only stores per-agent bindings — strings pointing at
``(server_name, tool_name)`` — which are validated against the same
LiteLLM view at bind time.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent, McpAgentToolBinding, User
from app.auth.dependencies import get_current_user, get_session_data
from app.auth.session_store import SessionData
from app.db.session import get_db
from app.schemas.mcp import (
    McpServerResponse,
    McpToolBindingResponse,
    McpToolBindRequest,
    McpToolResponse,
)
from app.services import mcp_catalog

router = APIRouter()

TOOL_NAME_SEPARATOR = "__"


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def user_token(
    session: SessionData = Depends(get_session_data),
) -> str:
    """Raw OIDC access token for downstream calls to LiteLLM."""
    return session.access_token


_litellm_tools_for = mcp_catalog.fetch_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_qualified(qualified: str) -> tuple[str, str]:
    if TOOL_NAME_SEPARATOR not in qualified:
        raise HTTPException(
            status_code=400, detail=f"Invalid tool id: {qualified}"
        )
    server_name, tool_name = qualified.split(TOOL_NAME_SEPARATOR, 1)
    return server_name, tool_name


def _group_by_server(tools: list[dict]) -> dict[str, list[dict]]:
    """Group LiteLLM-prefixed tools by their ``{server}__`` prefix."""
    grouped: dict[str, list[dict]] = {}
    for t in tools:
        name = t.get("name") or ""
        if TOOL_NAME_SEPARATOR not in name:
            continue
        server_name, _ = name.split(TOOL_NAME_SEPARATOR, 1)
        grouped.setdefault(server_name, []).append(t)
    return grouped


def _tool_to_response(tool: dict, server_name: str) -> McpToolResponse:
    prefixed = tool["name"]
    prefix = f"{server_name}{TOOL_NAME_SEPARATOR}"
    raw = prefixed[len(prefix):] if prefixed.startswith(prefix) else prefixed
    return McpToolResponse(
        id=prefixed,
        server_id=server_name,  # server_name is the binding-stable identifier
        server_name=server_name,
        name=raw,
        description=tool.get("description"),
        input_schema=tool.get("inputSchema") or {},
        qualified_name=prefixed,
    )


# ---------------------------------------------------------------------------
# Catalog — sourced entirely from LiteLLM via the caller's JWT
# ---------------------------------------------------------------------------


@router.get("/servers", response_model=list[McpServerResponse])
async def list_servers(token: str = Depends(user_token)):
    tools = await _litellm_tools_for(token)
    grouped = _group_by_server(tools)
    out = [
        McpServerResponse(
            id=name,
            name=name,
            description=None,  # Not exposed on the MCP protocol view
            tags=[],
            tool_count=len(group),
        )
        for name, group in grouped.items()
    ]
    out.sort(key=lambda r: r.name)
    return out


@router.get("/servers/{server_name}/tools", response_model=list[McpToolResponse])
async def list_server_tools(server_name: str, token: str = Depends(user_token)):
    tools = await _litellm_tools_for(token)
    grouped = _group_by_server(tools)
    if server_name not in grouped:
        raise HTTPException(status_code=404, detail="Server not found or not accessible")
    return [_tool_to_response(t, server_name) for t in grouped[server_name]]


@router.get("/tools/search", response_model=list[McpToolResponse])
async def search_tools(
    q: str = Query(..., min_length=1),
    token: str = Depends(user_token),
):
    tools = await _litellm_tools_for(token)
    q_lower = q.lower()
    out: list[McpToolResponse] = []
    for t in tools:
        name = t.get("name") or ""
        desc = t.get("description") or ""
        if TOOL_NAME_SEPARATOR not in name:
            continue
        server_name = name.split(TOOL_NAME_SEPARATOR, 1)[0]
        if q_lower in name.lower() or q_lower in desc.lower():
            out.append(_tool_to_response(t, server_name))
    out.sort(key=lambda r: r.qualified_name)
    return out[:50]


# ---------------------------------------------------------------------------
# Per-agent bindings
# ---------------------------------------------------------------------------


async def _owned_agent(db: AsyncSession, agent_id: uuid.UUID, user: User) -> Agent:
    agent = (
        await db.execute(select(Agent).where(Agent.id == agent_id))
    ).scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not the owner of this agent")
    return agent


def _bindings_to_responses(
    bindings: Iterable[McpAgentToolBinding], tools_by_name: dict[str, dict],
) -> list[McpToolBindingResponse]:
    out: list[McpToolBindingResponse] = []
    for b in bindings:
        qualified = f"{b.server_name}{TOOL_NAME_SEPARATOR}{b.tool_name}"
        entry = tools_by_name.get(qualified)
        if entry is None:
            # Tool is no longer visible (server revoked, deleted, or renamed).
            # Surface as a stub so the UI can prompt cleanup.
            tool = McpToolResponse(
                id=qualified,
                server_id=b.server_name,
                server_name=b.server_name,
                name=b.tool_name,
                description=None,
                input_schema={},
                qualified_name=qualified,
            )
        else:
            tool = _tool_to_response(entry, b.server_name)
        out.append(
            McpToolBindingResponse(
                id=str(b.id), agent_id=str(b.agent_id), tool=tool,
            )
        )
    return out


@router.get("/agents/{agent_id}/tools", response_model=list[McpToolBindingResponse])
async def list_agent_tools(
    agent_id: uuid.UUID,
    user: User = Depends(get_current_user),
    token: str = Depends(user_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_agent(db, agent_id, user)
    bindings = (
        await db.execute(
            select(McpAgentToolBinding)
            .where(McpAgentToolBinding.agent_id == agent_id)
            .order_by(McpAgentToolBinding.server_name, McpAgentToolBinding.tool_name)
        )
    ).scalars().all()
    tools = await _litellm_tools_for(token)
    by_name = {t["name"]: t for t in tools}
    return _bindings_to_responses(bindings, by_name)


@router.put("/agents/{agent_id}/tools", response_model=list[McpToolBindingResponse])
async def set_agent_tools(
    agent_id: uuid.UUID,
    body: McpToolBindRequest,
    user: User = Depends(get_current_user),
    token: str = Depends(user_token),
    db: AsyncSession = Depends(get_db),
):
    await _owned_agent(db, agent_id, user)

    # Fetch the user's view once, validate every requested tool against it.
    tools = await _litellm_tools_for(token)
    visible = {t["name"] for t in tools}
    parsed: list[tuple[str, str]] = []
    for qualified in body.tool_ids:
        if qualified not in visible:
            raise HTTPException(
                status_code=403,
                detail=f"Tool '{qualified}' is not accessible",
            )
        parsed.append(_split_qualified(qualified))

    await db.execute(
        delete(McpAgentToolBinding).where(McpAgentToolBinding.agent_id == agent_id)
    )
    for server_name, tool_name in parsed:
        db.add(
            McpAgentToolBinding(
                agent_id=agent_id, server_name=server_name, tool_name=tool_name,
            )
        )
    await db.flush()

    return await list_agent_tools(agent_id, user, token, db)


@router.delete("/agents/{agent_id}/tools/{qualified_name}", status_code=204)
async def unbind_tool(
    agent_id: uuid.UUID,
    qualified_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_agent(db, agent_id, user)
    server_name, tool_name = _split_qualified(qualified_name)

    result = await db.execute(
        delete(McpAgentToolBinding).where(
            McpAgentToolBinding.agent_id == agent_id,
            McpAgentToolBinding.server_name == server_name,
            McpAgentToolBinding.tool_name == tool_name,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Binding not found")
    await db.flush()
    return None

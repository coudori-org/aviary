"""MCP Gateway Server — dynamic tools/list and tools/call with ACL filtering
and transparent credential injection from Vault.

Uses the low-level mcp.server.Server API (not FastMCP decorators) to handle
tool requests dynamically based on agent bindings and user ACL.

Credential injection:
  config/secret-injection.yaml maps {server}.args.{param} → vault_key.
  - tools/list: injected params are stripped from inputSchema (invisible to Claude)
  - tools/call: injected params are fetched from Vault and merged into arguments
    before proxying to the backend MCP server.
"""

import logging
import uuid

from mcp.server import Server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from aviary_shared.db.models import McpAgentToolBinding, McpServer, McpTool
from app.db.session import async_session_factory
from app.mcp.connection_pool import pool
from app.services.acl import check_tool_access
from app.services.secret_injection import (
    get_injected_args,
    strip_injected_from_schema,
)
from app.services.vault_client import get_mcp_credential

logger = logging.getLogger(__name__)

TOOL_NAME_SEPARATOR = "__"


# ── Server factory ───────────────────────────────────────────

def create_gateway_server() -> Server:
    """Create and configure the MCP gateway server instance."""
    server = Server("aviary-mcp-gateway")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return tools bound to the agent, filtered by user ACL.

        Injected arguments (from credential-tools.yaml) are stripped from
        inputSchema so Claude doesn't know about them.
        """
        ctx = getattr(server, "_request_context", {})
        agent_id = ctx.get("agent_id")
        user_external_id = ctx.get("user_external_id")

        if not agent_id or not user_external_id:
            logger.warning("list_tools called without agent_id or user_external_id")
            return []

        agent_uuid = uuid.UUID(agent_id)
        tools: list[Tool] = []

        async with async_session_factory() as db:
            result = await db.execute(
                select(McpAgentToolBinding)
                .where(McpAgentToolBinding.agent_id == agent_uuid)
                .options(
                    joinedload(McpAgentToolBinding.tool).joinedload(McpTool.server)
                )
            )
            bindings = result.scalars().unique().all()

            for binding in bindings:
                tool = binding.tool
                srv = tool.server

                if srv.status != "active":
                    continue

                perm = await check_tool_access(
                    db, user_external_id, srv.id, tool.id
                )
                if perm != "use":
                    continue

                qualified_name = f"{srv.name}{TOOL_NAME_SEPARATOR}{tool.name}"

                # Strip vault-injected args from schema
                injected = get_injected_args(srv.name, tool.name)
                schema = strip_injected_from_schema(tool.input_schema or {}, injected)

                tools.append(Tool(
                    name=qualified_name,
                    description=tool.description or "",
                    inputSchema=schema,
                ))

        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
        """Route a tool call to the correct backend MCP server.

        Vault-managed arguments are fetched and injected before proxying.
        """
        ctx = getattr(server, "_request_context", {})
        agent_id = ctx.get("agent_id")
        user_external_id = ctx.get("user_external_id")

        if not agent_id or not user_external_id:
            return [TextContent(type="text", text="Error: missing authentication context")]

        if TOOL_NAME_SEPARATOR not in name:
            return [TextContent(type="text", text=f"Error: invalid tool name format: {name}")]

        server_name, tool_name = name.split(TOOL_NAME_SEPARATOR, 1)

        async with async_session_factory() as db:
            result = await db.execute(
                select(McpServer).where(McpServer.name == server_name)
            )
            mcp_server = result.scalar_one_or_none()
            if mcp_server is None:
                return [TextContent(type="text", text=f"Error: unknown server: {server_name}")]

            if mcp_server.status != "active":
                return [TextContent(type="text", text=f"Error: server {server_name} is not active")]

            result = await db.execute(
                select(McpTool).where(
                    McpTool.server_id == mcp_server.id,
                    McpTool.name == tool_name,
                )
            )
            mcp_tool = result.scalar_one_or_none()
            if mcp_tool is None:
                return [TextContent(type="text", text=f"Error: unknown tool: {tool_name}")]

            agent_uuid = uuid.UUID(agent_id)
            result = await db.execute(
                select(McpAgentToolBinding).where(
                    McpAgentToolBinding.agent_id == agent_uuid,
                    McpAgentToolBinding.tool_id == mcp_tool.id,
                )
            )
            if result.scalar_one_or_none() is None:
                return [TextContent(type="text", text=f"Error: tool {name} not bound to agent")]

            perm = await check_tool_access(
                db, user_external_id, mcp_server.id, mcp_tool.id
            )
            if perm != "use":
                return [TextContent(type="text", text=f"Error: permission denied for tool {name}")]

        # ── Inject vault credentials into arguments ──
        final_args = dict(arguments or {})
        injected = get_injected_args(server_name, tool_name)
        for arg_name, mapping in injected.items():
            vault_key = mapping["vault_key"]
            token = await get_mcp_credential(user_external_id, vault_key)
            if not token:
                return [TextContent(
                    type="text",
                    text=f"Error: no '{vault_key}' credential found for your account. "
                         f"Ask your admin to configure it.",
                )]
            final_args[arg_name] = token

        # ── Forward to backend MCP server ──
        try:
            call_result: CallToolResult = await pool.call_tool(
                mcp_server, tool_name, final_args,
            )
            contents = []
            for item in call_result.content:
                if hasattr(item, "text"):
                    contents.append(TextContent(type="text", text=item.text))
                else:
                    contents.append(TextContent(type="text", text=str(item)))
            return contents
        except Exception as e:  # Best-effort: return error to caller instead of crashing
            logger.exception("Tool call failed: %s on %s", tool_name, server_name)
            return [TextContent(type="text", text=f"Error: tool call failed: {e}")]

    return server

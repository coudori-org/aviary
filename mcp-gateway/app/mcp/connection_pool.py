"""Connection pool for backend MCP servers."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.sse import sse_client
from mcp.types import CallToolResult

from aviary_shared.db.models import McpServer

logger = logging.getLogger(__name__)


class McpConnectionPool:
    """Manages connections to backend MCP servers.

    For each tool call, opens a fresh session to the backend.
    Stateless design — no persistent connections cached.
    """

    @asynccontextmanager
    async def _connect(self, server: McpServer) -> AsyncGenerator[ClientSession, None]:
        """Open a session to a backend MCP server."""
        transport = server.transport_type
        config = server.connection_config

        headers = config.get("headers", {})

        if transport == "streamable_http":
            url = config["url"]
            async with streamablehttp_client(url=url, headers=headers) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        elif transport == "sse":
            url = config["url"]
            async with sse_client(url=url, headers=headers) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        else:
            raise ValueError(f"Unsupported transport: {transport}")

    async def list_tools(self, server: McpServer) -> list[dict]:
        """Connect to a backend server and return its tool list."""
        try:
            async with self._connect(server) as session:
                result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {},
                    }
                    for tool in result.tools
                ]
        except Exception:  # Log and re-raise: MCP SDK can throw transport/protocol errors
            logger.exception("Failed to list tools from server %s (%s)", server.name, server.id)
            raise

    async def call_tool(
        self,
        server: McpServer,
        tool_name: str,
        arguments: dict,
    ) -> CallToolResult:
        """Forward a tool call to a backend MCP server."""
        try:
            async with self._connect(server) as session:
                return await session.call_tool(tool_name, arguments)
        except Exception:  # Log and re-raise: MCP SDK can throw transport/protocol errors
            logger.exception(
                "Failed to call tool %s on server %s", tool_name, server.name
            )
            raise


# Singleton
pool = McpConnectionPool()

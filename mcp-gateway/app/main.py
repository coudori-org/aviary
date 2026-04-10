"""MCP Gateway — FastAPI application with MCP Streamable HTTP proxy endpoint."""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from mcp.types import ListToolsRequest, CallToolRequest

from app.auth.dependencies import get_current_user
from app.auth.oidc import init_oidc
from app.mcp.gateway_server import create_gateway_server

logger = logging.getLogger(__name__)

gateway_server = create_gateway_server()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_oidc()

    # Auto-register platform-provided MCP servers and discover tools
    from app.db.session import async_session_factory
    from app.services.platform_servers import register_platform_servers
    try:
        async with async_session_factory() as db:
            await register_platform_servers(db)
    except Exception:  # Best-effort: startup registration failure is retried on next startup
        logger.warning("Platform MCP server registration failed — will retry on next startup", exc_info=True)

    yield


app = FastAPI(title="Aviary MCP Gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/mcp/v1/{agent_id}", methods=["GET", "POST", "DELETE"])
async def mcp_proxy(agent_id: str, request: Request):
    """Streamable HTTP MCP endpoint.

    The claude-agent-sdk connects here as if it were a single MCP server.
    Authentication is via the user's OIDC JWT in the Authorization header.
    """
    # Authenticate
    try:
        claims = await get_current_user(request)
    except ValueError as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    # Inject context for the MCP server handlers
    gateway_server._request_context = {
        "agent_id": agent_id,
        "user_external_id": claims.sub,
    }

    if request.method == "GET":
        return Response(status_code=405, content="SSE not supported in stateless mode")

    if request.method == "DELETE":
        return Response(status_code=200)

    # POST — handle JSON-RPC request
    try:
        body = await request.body()
        json_body = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}},
        )

    # Process through MCP server
    try:
        response = await _handle_mcp_request(json_body)
        return JSONResponse(content=response)
    except Exception:  # Best-effort: catch-all for JSON-RPC error response
        logger.exception("MCP request processing failed")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": "Internal error"},
                "id": json_body.get("id"),
            },
        )


async def _handle_mcp_request(json_body: dict) -> dict:
    """Process a single MCP JSON-RPC request through the gateway server."""
    method = json_body.get("method", "")
    params = json_body.get("params", {})
    req_id = json_body.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "aviary-mcp-gateway", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        # Client acknowledgement, no response needed for notifications
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        tools_handler = gateway_server.request_handlers.get(ListToolsRequest)
        if tools_handler:
            result = await tools_handler(ListToolsRequest(method="tools/list", params=params))
            tools = result.root.tools if hasattr(result, "root") else []
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": t.inputSchema or {},
                        }
                        for t in tools
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": []},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        call_handler = gateway_server.request_handlers.get(CallToolRequest)
        if call_handler:
            result = await call_handler(CallToolRequest(method="tools/call", params={"name": tool_name, "arguments": arguments}))
            call_result = result.root if hasattr(result, "root") else result
            contents = call_result.content if hasattr(call_result, "content") else []
            is_error = getattr(call_result, "isError", False) or any(
                hasattr(c, "text") and c.text.startswith("Error:") for c in contents
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {"type": "text", "text": c.text} if hasattr(c, "text") else {"type": "text", "text": str(c)}
                        for c in contents
                    ],
                    "isError": is_error,
                },
            }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }

"""Confluence MCP Server — platform-provided stub.

Provides Confluence wiki operations: page CRUD, search, space management,
and content hierarchy navigation.
"""

import json

from mcp.server import Server
from mcp.types import TextContent, Tool

server = Server("confluence")

TOOLS = [
    Tool(
        name="get_page",
        description="Get a Confluence page by ID or title",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID"},
                "space_key": {"type": "string", "description": "Space key (used with title)"},
                "title": {"type": "string", "description": "Page title (used with space_key)"},
                "expand": {"type": "array", "items": {"type": "string"}, "description": "Fields to expand (e.g., body.storage, version)"},
            },
        },
    ),
    Tool(
        name="create_page",
        description="Create a new Confluence page",
        inputSchema={
            "type": "object",
            "properties": {
                "space_key": {"type": "string", "description": "Space key"},
                "title": {"type": "string", "description": "Page title"},
                "body": {"type": "string", "description": "Page content (Confluence storage format or plain text)"},
                "parent_id": {"type": "string", "description": "Parent page ID for hierarchy"},
                "content_format": {"type": "string", "enum": ["storage", "wiki", "plain"], "default": "storage"},
            },
            "required": ["space_key", "title", "body"],
        },
    ),
    Tool(
        name="update_page",
        description="Update an existing Confluence page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID to update"},
                "title": {"type": "string", "description": "New title (optional)"},
                "body": {"type": "string", "description": "New content"},
                "version_comment": {"type": "string", "description": "Version comment"},
                "content_format": {"type": "string", "enum": ["storage", "wiki", "plain"], "default": "storage"},
            },
            "required": ["page_id", "body"],
        },
    ),
    Tool(
        name="delete_page",
        description="Delete a Confluence page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID to delete"},
            },
            "required": ["page_id"],
        },
    ),
    Tool(
        name="search",
        description="Search Confluence content using CQL (Confluence Query Language)",
        inputSchema={
            "type": "object",
            "properties": {
                "cql": {"type": "string", "description": "CQL query (e.g., 'type=page AND space=DEV AND text~\"auth\"')"},
                "limit": {"type": "integer", "default": 20, "description": "Maximum results"},
            },
            "required": ["cql"],
        },
    ),
    Tool(
        name="get_child_pages",
        description="Get child pages of a parent page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Parent page ID"},
                "limit": {"type": "integer", "default": 25},
            },
            "required": ["page_id"],
        },
    ),
    Tool(
        name="list_spaces",
        description="List all Confluence spaces",
        inputSchema={
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["global", "personal"], "description": "Space type filter"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    ),
    Tool(
        name="get_space",
        description="Get details of a Confluence space",
        inputSchema={
            "type": "object",
            "properties": {
                "space_key": {"type": "string", "description": "Space key"},
            },
            "required": ["space_key"],
        },
    ),
    Tool(
        name="add_label",
        description="Add a label to a Confluence page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID"},
                "label": {"type": "string", "description": "Label to add"},
            },
            "required": ["page_id", "label"],
        },
    ),
    Tool(
        name="get_page_history",
        description="Get version history of a page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["page_id"],
        },
    ),
    Tool(
        name="add_comment",
        description="Add a comment to a Confluence page",
        inputSchema={
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page ID"},
                "body": {"type": "string", "description": "Comment content"},
            },
            "required": ["page_id", "body"],
        },
    ),
]

FAKE_RESPONSES = {
    "get_page": json.dumps({
        "id": "12345",
        "title": "Architecture Overview",
        "space": {"key": "ENG", "name": "Engineering"},
        "version": {"number": 5, "when": "2026-03-30T14:00:00Z"},
        "body": {"storage": {"value": "<h1>Architecture</h1><p>This document describes the system architecture...</p>"}},
    }, indent=2),
    "create_page": json.dumps({
        "id": "12346",
        "title": "New Page",
        "space": {"key": "ENG"},
        "_links": {"webui": "/spaces/ENG/pages/12346/New+Page"},
    }, indent=2),
    "update_page": json.dumps({
        "id": "12345",
        "title": "Architecture Overview",
        "version": {"number": 6, "when": "2026-04-05T10:00:00Z"},
    }, indent=2),
    "delete_page": "Page 12345 deleted successfully.",
    "search": json.dumps({
        "totalSize": 3,
        "results": [
            {"id": "12345", "title": "Architecture Overview", "space": {"key": "ENG"}, "type": "page"},
            {"id": "12350", "title": "API Design Guide", "space": {"key": "ENG"}, "type": "page"},
            {"id": "12360", "title": "Auth Flow Diagram", "space": {"key": "SEC"}, "type": "page"},
        ],
    }, indent=2),
    "get_child_pages": json.dumps({
        "results": [
            {"id": "12346", "title": "Backend Architecture"},
            {"id": "12347", "title": "Frontend Architecture"},
            {"id": "12348", "title": "Infrastructure"},
        ],
    }, indent=2),
    "list_spaces": json.dumps([
        {"key": "ENG", "name": "Engineering", "type": "global"},
        {"key": "SEC", "name": "Security", "type": "global"},
        {"key": "OPS", "name": "Operations", "type": "global"},
    ], indent=2),
    "get_space": json.dumps({
        "key": "ENG",
        "name": "Engineering",
        "type": "global",
        "description": "Engineering team documentation",
        "_links": {"webui": "/spaces/ENG"},
    }, indent=2),
    "add_label": "Label 'architecture' added to page 12345.",
    "get_page_history": json.dumps({
        "results": [
            {"number": 5, "when": "2026-03-30T14:00:00Z", "by": {"displayName": "Alice"}, "message": "Updated diagrams"},
            {"number": 4, "when": "2026-03-28T09:00:00Z", "by": {"displayName": "Bob"}, "message": "Added API section"},
        ],
    }, indent=2),
    "add_comment": "Comment added to page 12345.",
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    response = FAKE_RESPONSES.get(name, f"[stub] Tool '{name}' called with: {json.dumps(arguments)}")
    return [TextContent(type="text", text=response)]


def create_app():
    """Create a Starlette ASGI app for Streamable HTTP transport."""
    import json as _json
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def health(request: Request):
        return JSONResponse({"status": "ok"})

    async def mcp_endpoint(request: Request):
        body = await request.json()
        method = body.get("method", "")
        params = body.get("params", {})
        req_id = body.get("id")

        if method == "initialize":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "confluence", "version": "0.1.0"},
            }})
        if method == "notifications/initialized":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
        if method == "tools/list":
            tools = await list_tools()
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {
                "tools": [{"name": t.name, "description": t.description, "inputSchema": t.inputSchema} for t in tools]
            }})
        if method == "tools/call":
            contents = await call_tool(params.get("name", ""), params.get("arguments", {}))
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": c.text} for c in contents],
                "isError": False,
            }})
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}})

    return Starlette(routes=[
        Route("/health", health),
        Route("/mcp", mcp_endpoint, methods=["GET", "POST"]),
    ])


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("MCP_SERVER_PORT", "8003"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)

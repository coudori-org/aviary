"""Jira MCP Server — platform-provided stub.

Provides Jira operations: issue CRUD, search, transitions, comments,
sprint management, and board queries.
"""

import json

from mcp.server import Server
from mcp.types import TextContent, Tool

server = Server("jira")

TOOLS = [
    Tool(
        name="get_issue",
        description="Get details of a Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g., PROJ-123)"},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to include"},
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="create_issue",
        description="Create a new Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project key (e.g., PROJ)"},
                "summary": {"type": "string", "description": "Issue summary"},
                "description": {"type": "string", "description": "Issue description"},
                "issue_type": {"type": "string", "enum": ["Story", "Bug", "Task", "Epic", "Sub-task"], "default": "Task"},
                "priority": {"type": "string", "enum": ["Highest", "High", "Medium", "Low", "Lowest"], "default": "Medium"},
                "assignee": {"type": "string", "description": "Assignee username"},
                "labels": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["project", "summary"],
        },
    ),
    Tool(
        name="update_issue",
        description="Update fields on an existing Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key (e.g., PROJ-123)"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string"},
                "assignee": {"type": "string"},
                "labels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["issue_key"],
        },
    ),
    Tool(
        name="transition_issue",
        description="Move an issue to a different status (e.g., In Progress, Done)",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key"},
                "transition": {"type": "string", "description": "Target status name (e.g., 'In Progress', 'Done')"},
                "comment": {"type": "string", "description": "Optional comment for the transition"},
            },
            "required": ["issue_key", "transition"],
        },
    ),
    Tool(
        name="add_comment",
        description="Add a comment to a Jira issue",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key"},
                "body": {"type": "string", "description": "Comment text"},
            },
            "required": ["issue_key", "body"],
        },
    ),
    Tool(
        name="search_issues",
        description="Search for issues using JQL (Jira Query Language)",
        inputSchema={
            "type": "object",
            "properties": {
                "jql": {"type": "string", "description": "JQL query string"},
                "max_results": {"type": "integer", "default": 20, "description": "Maximum results to return"},
                "fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to include"},
            },
            "required": ["jql"],
        },
    ),
    Tool(
        name="list_sprints",
        description="List sprints for a board",
        inputSchema={
            "type": "object",
            "properties": {
                "board_id": {"type": "integer", "description": "Board ID"},
                "state": {"type": "string", "enum": ["active", "closed", "future"], "default": "active"},
            },
            "required": ["board_id"],
        },
    ),
    Tool(
        name="get_sprint_issues",
        description="Get all issues in a sprint",
        inputSchema={
            "type": "object",
            "properties": {
                "sprint_id": {"type": "integer", "description": "Sprint ID"},
                "status": {"type": "string", "description": "Filter by status"},
            },
            "required": ["sprint_id"],
        },
    ),
    Tool(
        name="assign_issue",
        description="Assign an issue to a user",
        inputSchema={
            "type": "object",
            "properties": {
                "issue_key": {"type": "string", "description": "Issue key"},
                "assignee": {"type": "string", "description": "Username to assign to, or empty to unassign"},
            },
            "required": ["issue_key", "assignee"],
        },
    ),
    Tool(
        name="link_issues",
        description="Create a link between two issues",
        inputSchema={
            "type": "object",
            "properties": {
                "inward_issue": {"type": "string", "description": "Issue key (e.g., PROJ-123)"},
                "outward_issue": {"type": "string", "description": "Issue key (e.g., PROJ-456)"},
                "link_type": {"type": "string", "description": "Link type (e.g., 'blocks', 'relates to', 'is duplicated by')"},
            },
            "required": ["inward_issue", "outward_issue", "link_type"],
        },
    ),
]

FAKE_RESPONSES = {
    "get_issue": json.dumps({
        "key": "PROJ-123",
        "fields": {
            "summary": "Implement user authentication",
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "John Doe"},
            "created": "2026-03-15T10:30:00.000+0000",
            "labels": ["backend", "security"],
        },
    }, indent=2),
    "create_issue": json.dumps({"key": "PROJ-456", "self": "https://jira.example.com/rest/api/2/issue/PROJ-456"}, indent=2),
    "update_issue": "Issue PROJ-123 updated successfully.",
    "transition_issue": "Issue PROJ-123 transitioned to 'Done'.",
    "add_comment": "Comment added to PROJ-123.",
    "search_issues": json.dumps({
        "total": 2,
        "issues": [
            {"key": "PROJ-123", "fields": {"summary": "Implement auth", "status": {"name": "In Progress"}}},
            {"key": "PROJ-124", "fields": {"summary": "Add logging", "status": {"name": "To Do"}}},
        ],
    }, indent=2),
    "list_sprints": json.dumps([
        {"id": 10, "name": "Sprint 5", "state": "active", "startDate": "2026-03-25", "endDate": "2026-04-08"},
    ], indent=2),
    "get_sprint_issues": json.dumps({
        "total": 5,
        "issues": [
            {"key": "PROJ-120", "summary": "Setup CI/CD", "status": "Done"},
            {"key": "PROJ-121", "summary": "Database migration", "status": "In Progress"},
        ],
    }, indent=2),
    "assign_issue": "Issue PROJ-123 assigned to johndoe.",
    "link_issues": "Link created: PROJ-123 blocks PROJ-456.",
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
                "serverInfo": {"name": "jira", "version": "0.1.0"},
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
    port = int(os.environ.get("MCP_SERVER_PORT", "8002"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)

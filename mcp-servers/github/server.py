"""GitHub MCP Server — platform-provided stub.

Provides GitHub REST API operations (PRs, issues, code search, reviews)
and git credential provisioning. Git CLI operations (clone, pull, push,
commit, branch) are NOT handled here — they run directly in the agent's
sandbox via Claude Code's built-in Bash tool, authenticated by credentials
issued through setup_git_credentials.
"""

import json

from mcp.server import Server
from mcp.types import TextContent, Tool

server = Server("github")

TOOLS = [
    # ── Credential provisioning ──────────────────────────────
    Tool(
        name="setup_git_credentials",
        description=(
            "Configure git credentials in the agent workspace for GitHub access. "
            "After calling this, the agent can use git clone/pull/push directly via shell. "
            "Returns a shell command to run that configures the credential helper."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository in owner/repo format (optional, for scoped tokens)",
                },
            },
        },
    ),
    # ── Pull Requests ────────────────────────────────────────
    Tool(
        name="create_pull_request",
        description="Create a pull request on GitHub",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "title": {"type": "string", "description": "PR title"},
                "body": {"type": "string", "description": "PR description"},
                "head": {"type": "string", "description": "Source branch"},
                "base": {"type": "string", "description": "Target branch", "default": "main"},
                "draft": {"type": "boolean", "default": False},
            },
            "required": ["repo", "title", "head"],
        },
    ),
    Tool(
        name="list_pull_requests",
        description="List pull requests for a repository",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
            },
            "required": ["repo"],
        },
    ),
    Tool(
        name="get_pull_request",
        description="Get details of a specific pull request including diff stats",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "PR number"},
            },
            "required": ["repo", "number"],
        },
    ),
    Tool(
        name="merge_pull_request",
        description="Merge a pull request",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "PR number"},
                "merge_method": {"type": "string", "enum": ["merge", "squash", "rebase"], "default": "squash"},
            },
            "required": ["repo", "number"],
        },
    ),
    Tool(
        name="list_pr_reviews",
        description="List reviews on a pull request",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "PR number"},
            },
            "required": ["repo", "number"],
        },
    ),
    Tool(
        name="create_pr_review",
        description="Submit a review on a pull request (approve, request changes, or comment)",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "PR number"},
                "event": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"]},
                "body": {"type": "string", "description": "Review comment"},
            },
            "required": ["repo", "number", "event"],
        },
    ),
    # ── Issues ───────────────────────────────────────────────
    Tool(
        name="create_issue",
        description="Create a new issue on GitHub",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "title": {"type": "string", "description": "Issue title"},
                "body": {"type": "string", "description": "Issue body (markdown)"},
                "labels": {"type": "array", "items": {"type": "string"}, "default": []},
                "assignees": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            "required": ["repo", "title"],
        },
    ),
    Tool(
        name="list_issues",
        description="List issues for a repository",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "state": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                "labels": {"type": "string", "description": "Comma-separated labels to filter"},
                "assignee": {"type": "string", "description": "Filter by assignee username"},
            },
            "required": ["repo"],
        },
    ),
    Tool(
        name="get_issue",
        description="Get details of a specific issue",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "Issue number"},
            },
            "required": ["repo", "number"],
        },
    ),
    Tool(
        name="add_issue_comment",
        description="Add a comment to an issue or pull request",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "number": {"type": "integer", "description": "Issue or PR number"},
                "body": {"type": "string", "description": "Comment body (markdown)"},
            },
            "required": ["repo", "number", "body"],
        },
    ),
    # ── Code & Repository ────────────────────────────────────
    Tool(
        name="get_file_contents",
        description="Get contents of a file from a GitHub repository via API (without cloning)",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
                "path": {"type": "string", "description": "File path in the repository"},
                "ref": {"type": "string", "description": "Branch, tag, or commit SHA", "default": "main"},
            },
            "required": ["repo", "path"],
        },
    ),
    Tool(
        name="search_code",
        description="Search for code across GitHub repositories",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (GitHub code search syntax)"},
                "repo": {"type": "string", "description": "Limit search to a specific repo (owner/repo)"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_repos",
        description="List repositories for a user or organization",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "User or organization name"},
                "type": {"type": "string", "enum": ["all", "owner", "member"], "default": "all"},
                "sort": {"type": "string", "enum": ["created", "updated", "pushed", "full_name"], "default": "updated"},
            },
            "required": ["owner"],
        },
    ),
    Tool(
        name="get_repo",
        description="Get repository metadata (description, stars, language, default branch)",
        inputSchema={
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository in owner/repo format"},
            },
            "required": ["repo"],
        },
    ),
]

FAKE_RESPONSES = {
    "setup_git_credentials": (
        "Git credentials configured. Run the following command in your shell:\n\n"
        "git config --global credential.helper store && "
        "echo 'https://x-access-token:ghp_stub_token_xxxxx@github.com' > ~/.git-credentials\n\n"
        "After this, git clone/pull/push to GitHub will work without prompts."
    ),
    "create_pull_request": json.dumps(
        {"number": 42, "html_url": "https://github.com/org/repo/pull/42", "state": "open"}, indent=2
    ),
    "list_pull_requests": json.dumps([
        {"number": 42, "title": "Add auth module", "state": "open", "user": {"login": "dev1"}, "created_at": "2026-04-01T10:00:00Z"},
        {"number": 41, "title": "Fix login bug", "state": "open", "user": {"login": "dev2"}, "created_at": "2026-03-30T15:00:00Z"},
    ], indent=2),
    "get_pull_request": json.dumps(
        {"number": 42, "title": "Add auth module", "state": "open", "additions": 150, "deletions": 30, "changed_files": 8, "mergeable": True}, indent=2
    ),
    "merge_pull_request": json.dumps({"merged": True, "sha": "abc123def456", "message": "Squash and merge"}, indent=2),
    "list_pr_reviews": json.dumps([
        {"user": {"login": "reviewer1"}, "state": "APPROVED", "submitted_at": "2026-04-02T09:00:00Z"},
    ], indent=2),
    "create_pr_review": json.dumps({"id": 1001, "state": "APPROVED"}, indent=2),
    "create_issue": json.dumps({"number": 101, "html_url": "https://github.com/org/repo/issues/101"}, indent=2),
    "list_issues": json.dumps([
        {"number": 101, "title": "Auth timeout on mobile", "state": "open", "labels": [{"name": "bug"}]},
        {"number": 100, "title": "Add dark mode support", "state": "open", "labels": [{"name": "enhancement"}]},
    ], indent=2),
    "get_issue": json.dumps(
        {"number": 101, "title": "Auth timeout on mobile", "state": "open", "body": "Users report auth timeouts...", "labels": [{"name": "bug"}], "assignees": [{"login": "dev1"}]}, indent=2
    ),
    "add_issue_comment": json.dumps({"id": 5001, "created_at": "2026-04-05T12:00:00Z"}, indent=2),
    "get_file_contents": "# README\n\nThis is the project README file.\n\n## Getting Started\n\n```bash\nnpm install\nnpm start\n```",
    "search_code": json.dumps({"total_count": 3, "items": [
        {"repository": {"full_name": "org/repo"}, "path": "src/auth.py", "text_matches": [{"fragment": "def authenticate(user):"}]},
    ]}, indent=2),
    "list_repos": json.dumps([
        {"full_name": "org/frontend", "description": "Web application", "language": "TypeScript", "updated_at": "2026-04-04"},
        {"full_name": "org/backend", "description": "API server", "language": "Python", "updated_at": "2026-04-03"},
    ], indent=2),
    "get_repo": json.dumps(
        {"full_name": "org/repo", "description": "Main project", "language": "Python", "default_branch": "main", "stargazers_count": 42}, indent=2
    ),
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
                "serverInfo": {"name": "github", "version": "0.1.0"},
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
    port = int(os.environ.get("MCP_SERVER_PORT", "8001"))
    uvicorn.run(create_app(), host="0.0.0.0", port=port)

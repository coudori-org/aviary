"""Jira legacy MCP tools — REST API v2 (Server / Data Center).

Cloud-parity quirks worth knowing:
  - Bodies are wiki markup, not ADF — markdown is forwarded as-is.
  - Users are identified by `name`; `account_id` parameter name is kept
    for surface parity but the value travels as `name` on the wire.
  - `search_issues` paginates via `startAt`; `next_page_token` carries
    that integer as a string.
"""

import json

from mcp.server.fastmcp import FastMCP

from common import request, result

mcp = FastMCP("jira", host="0.0.0.0", port=8000, stateless_http=True)


@mcp.tool()
async def get_issue(
    jira_token: str,
    issue_key: str,
    fields: list[str] | None = None,
) -> str:
    """Get a Jira issue by key (e.g. 'PROJ-123').

    Optional `fields` is a list of field names to limit the response
    (e.g. ['summary','status','assignee']). Omit for all fields.
    """
    params: dict = {}
    if fields:
        params["fields"] = ",".join(fields)
    res = await request(
        "GET",
        f"/rest/api/2/issue/{issue_key}",
        token=jira_token,
        params=params or None,
    )
    return result(res)


@mcp.tool()
async def create_issue(
    jira_token: str,
    project: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str | None = None,
    assignee_account_id: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Create a new Jira issue.

    `project` is the project key. `description` is sent verbatim as wiki
    markup. `assignee_account_id` is the Server username (see module docstring).
    """
    fields: dict = {
        "project": {"key": project},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = description
    if priority:
        fields["priority"] = {"name": priority}
    if assignee_account_id:
        fields["assignee"] = {"name": assignee_account_id}
    if labels:
        fields["labels"] = labels
    res = await request(
        "POST",
        "/rest/api/2/issue",
        token=jira_token,
        json_body={"fields": fields},
    )
    return result(res)


@mcp.tool()
async def update_issue(
    jira_token: str,
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    assignee_account_id: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Update fields on an existing Jira issue. Only the fields you set are sent.

    `description` is wiki markup. Pass an empty string for `assignee_account_id`
    to unassign.
    """
    fields: dict = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = description
    if priority is not None:
        fields["priority"] = {"name": priority}
    if assignee_account_id is not None:
        fields["assignee"] = {"name": assignee_account_id} if assignee_account_id else None
    if labels is not None:
        fields["labels"] = labels
    if not fields:
        return "ERROR: no fields provided to update"
    res = await request(
        "PUT",
        f"/rest/api/2/issue/{issue_key}",
        token=jira_token,
        json_body={"fields": fields},
    )
    if isinstance(res, str):
        return res
    return f"Issue {issue_key} updated."


@mcp.tool()
async def delete_issue(jira_token: str, issue_key: str) -> str:
    """Delete a Jira issue. This is permanent — use with care."""
    res = await request(
        "DELETE",
        f"/rest/api/2/issue/{issue_key}",
        token=jira_token,
    )
    if isinstance(res, str):
        return res
    return f"Issue {issue_key} deleted."


@mcp.tool()
async def get_transitions(jira_token: str, issue_key: str) -> str:
    """List the workflow transitions currently available for an issue.

    Returns [{id, name, to:{name}}, ...]. Pass the `name` to `transition_issue`.
    """
    res = await request(
        "GET",
        f"/rest/api/2/issue/{issue_key}/transitions",
        token=jira_token,
    )
    if isinstance(res, str):
        return res
    transitions = res.get("transitions", []) if isinstance(res, dict) else []
    return json.dumps([
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "to": {"name": (t.get("to") or {}).get("name")},
        }
        for t in transitions
    ])


@mcp.tool()
async def transition_issue(
    jira_token: str,
    issue_key: str,
    transition: str,
    comment: str = "",
) -> str:
    """Move an issue to a different status (e.g. 'In Progress', 'Done').

    `transition` is the human-readable transition name; we resolve it to the
    matching id. Optional `comment` is wiki markup.
    """
    tres = await request(
        "GET",
        f"/rest/api/2/issue/{issue_key}/transitions",
        token=jira_token,
    )
    if isinstance(tres, str):
        return tres
    available = tres.get("transitions", []) if isinstance(tres, dict) else []
    transition_id = None
    for t in available:
        if (t.get("name") or "").lower() == transition.lower():
            transition_id = t.get("id")
            break
    if not transition_id:
        names = [t.get("name") for t in available]
        return f"ERROR: transition '{transition}' not available for {issue_key}. Available: {names}"
    body: dict = {"transition": {"id": transition_id}}
    if comment:
        body["update"] = {"comment": [{"add": {"body": comment}}]}
    res = await request(
        "POST",
        f"/rest/api/2/issue/{issue_key}/transitions",
        token=jira_token,
        json_body=body,
    )
    if isinstance(res, str):
        return res
    return f"Issue {issue_key} transitioned to '{transition}'."


@mcp.tool()
async def add_comment(
    jira_token: str,
    issue_key: str,
    body: str,
) -> str:
    """Add a comment to a Jira issue. `body` is wiki markup (sent as-is)."""
    res = await request(
        "POST",
        f"/rest/api/2/issue/{issue_key}/comment",
        token=jira_token,
        json_body={"body": body},
    )
    return result(res)


@mcp.tool()
async def search_issues(
    jira_token: str,
    jql: str,
    max_results: int = 20,
    fields: list[str] | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for issues using JQL.

    Uses GET /rest/api/2/search with `startAt` paging. `next_page_token`, if
    given, is interpreted as the startAt integer. The response is normalized
    to {issues, nextPageToken?} so the agent's pagination flow works the
    same as on Cloud.
    """
    params: dict = {"jql": jql, "maxResults": max_results}
    if fields:
        params["fields"] = ",".join(fields)
    try:
        start_at = int(next_page_token) if next_page_token else 0
    except ValueError:
        return f"ERROR: next_page_token must be an integer string, got {next_page_token!r}"
    params["startAt"] = start_at
    res = await request(
        "GET",
        "/rest/api/2/search",
        token=jira_token,
        params=params,
    )
    if isinstance(res, str):
        return res
    issues = res.get("issues", []) if isinstance(res, dict) else []
    total = res.get("total") if isinstance(res, dict) else None
    page_size = res.get("maxResults", max_results) if isinstance(res, dict) else max_results
    out: dict = {"issues": issues}
    if isinstance(total, int) and start_at + page_size < total:
        out["nextPageToken"] = str(start_at + page_size)
    return json.dumps(out)


@mcp.tool()
async def assign_issue(
    jira_token: str,
    issue_key: str,
    account_id: str | None,
) -> str:
    """Assign a Jira issue to a user.

    On Server / DC the identifier is the username. The parameter is named
    `account_id` for parity with the Cloud variant. Pass an empty string or
    null to unassign.
    """
    payload = {"name": account_id if account_id else None}
    res = await request(
        "PUT",
        f"/rest/api/2/issue/{issue_key}/assignee",
        token=jira_token,
        json_body=payload,
    )
    if isinstance(res, str):
        return res
    return f"Issue {issue_key} assignee updated."


@mcp.tool()
async def find_user(jira_token: str, query: str) -> str:
    """Find Jira users by username, display name, or email.

    Server's /user/search uses the `username` query parameter and returns
    `name` instead of `accountId`. We map `name` → `accountId` in the response
    so `assign_issue` / `create_issue` can consume the result unchanged.
    """
    res = await request(
        "GET",
        "/rest/api/2/user/search",
        token=jira_token,
        params={"username": query},
    )
    if isinstance(res, str):
        return res
    users = res if isinstance(res, list) else []
    return json.dumps([
        {
            "accountId": u.get("name"),
            "displayName": u.get("displayName"),
            "emailAddress": u.get("emailAddress"),
        }
        for u in users
        if isinstance(u, dict)
    ])


@mcp.tool()
async def link_issues(
    jira_token: str,
    inward_issue: str,
    outward_issue: str,
    link_type: str,
) -> str:
    """Create a link between two issues."""
    body = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue},
        "outwardIssue": {"key": outward_issue},
    }
    res = await request(
        "POST",
        "/rest/api/2/issueLink",
        token=jira_token,
        json_body=body,
    )
    if isinstance(res, str):
        return res
    return f"Link created: {inward_issue} {link_type} {outward_issue}."


@mcp.tool()
async def list_sprints(
    jira_token: str,
    board_id: int,
    state: str = "active",
) -> str:
    """List sprints on a Jira board.

    `state` is one of 'active', 'closed', 'future', or comma-separated.
    """
    res = await request(
        "GET",
        f"/rest/agile/1.0/board/{board_id}/sprint",
        token=jira_token,
        params={"state": state},
    )
    return result(res)


@mcp.tool()
async def get_sprint_issues(
    jira_token: str,
    sprint_id: int,
    status: str | None = None,
) -> str:
    """Get all issues in a sprint. Optional `status` filters by issue status name."""
    params: dict = {}
    if status:
        params["jql"] = f'status = "{status}"'
    res = await request(
        "GET",
        f"/rest/agile/1.0/sprint/{sprint_id}/issue",
        token=jira_token,
        params=params or None,
    )
    return result(res)

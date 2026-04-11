"""Jira MCP Server.

Real Jira Cloud REST API v3 integration.

Auth: HTTP Basic with email + API token. Both are injected by the MCP Gateway as
the `jira_email` / `jira_token` arguments and stripped from the schema before
Claude sees the tool. The site URL comes from the JIRA_BASE_URL env var (shared
corporate Atlassian instance).

Rich text fields (description, comment body) accept markdown — `_md_to_adf`
converts them to Atlassian Document Format on the way out so tables, code,
lists, and inline formatting render correctly in Jira.
"""

import base64
import json
import os
from typing import Any

import httpx
from markdown_it import MarkdownIt
from mcp.server.fastmcp import FastMCP

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")

mcp = FastMCP("jira", host="0.0.0.0", port=8000, stateless_http=True)


# ── HTTP plumbing ──────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=JIRA_BASE_URL, timeout=30.0)
    return _http_client


def _basic_auth(email: str, token: str) -> str:
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


async def _request(
    method: str,
    path: str,
    *,
    email: str,
    token: str,
    json_body: Any = None,
    params: dict | None = None,
) -> dict | list | str:
    """Issue an authenticated Jira API request.

    Returns parsed JSON on 2xx, or an "ERROR: ..." string on failure. Tools
    propagate that string as their return value so the agent sees a readable
    error instead of an exception.
    """
    headers = {
        "Authorization": _basic_auth(email, token),
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    try:
        resp = await _client().request(
            method, path, headers=headers, json=json_body, params=params
        )
    except httpx.HTTPError as e:
        return f"ERROR: HTTP request failed: {e}"
    if resp.status_code >= 400:
        body = resp.text[:500] if resp.text else ""
        return f"ERROR: {resp.status_code} {resp.reason_phrase} — {body}"
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"text": resp.text}


def _result(value: dict | list | str) -> str:
    """Pass through error strings, otherwise JSON-encode."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


# ── Markdown → ADF ─────────────────────────────────────────────

_md = MarkdownIt("commonmark").enable("table").enable("strikethrough")


def _md_to_adf(md: str) -> dict:
    """Convert markdown to Atlassian Document Format.

    Walks the markdown-it-py token stream and emits ADF block nodes for
    paragraphs, headings, lists, code blocks, blockquotes, horizontal rules,
    and tables. Inline content supports text, bold, italic, strike, inline
    code, links, soft/hard breaks. Anything unrecognized is silently dropped
    rather than raising — the function never throws.
    """
    if not md:
        return {"type": "doc", "version": 1, "content": []}
    tokens = _md.parse(md)
    content = _walk_blocks(tokens, 0, len(tokens))
    if not content:
        content = [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": content}


def _find_block_close(tokens: list, open_idx: int, close_type: str) -> int:
    """Return the index of the matching close token for a block-level open."""
    level = tokens[open_idx].level
    for j in range(open_idx + 1, len(tokens)):
        if tokens[j].type == close_type and tokens[j].level == level:
            return j
    return len(tokens)


def _walk_blocks(tokens: list, start: int, end: int) -> list[dict]:
    out: list[dict] = []
    i = start
    while i < end:
        tok = tokens[i]
        ttype = tok.type
        if ttype == "paragraph_open":
            close = _find_block_close(tokens, i, "paragraph_close")
            inline = tokens[i + 1] if i + 1 < close else None
            children = inline.children if (inline and inline.type == "inline") else []
            out.append({"type": "paragraph", "content": _walk_inline(children or [])})
            i = close + 1
        elif ttype == "heading_open":
            close = _find_block_close(tokens, i, "heading_close")
            level = int(tok.tag[1:]) if tok.tag and tok.tag.startswith("h") else 1
            inline = tokens[i + 1] if i + 1 < close else None
            children = inline.children if (inline and inline.type == "inline") else []
            out.append({
                "type": "heading",
                "attrs": {"level": level},
                "content": _walk_inline(children or []),
            })
            i = close + 1
        elif ttype == "bullet_list_open":
            close = _find_block_close(tokens, i, "bullet_list_close")
            out.append({"type": "bulletList", "content": _walk_blocks(tokens, i + 1, close)})
            i = close + 1
        elif ttype == "ordered_list_open":
            close = _find_block_close(tokens, i, "ordered_list_close")
            out.append({
                "type": "orderedList",
                "attrs": {"order": 1},
                "content": _walk_blocks(tokens, i + 1, close),
            })
            i = close + 1
        elif ttype == "list_item_open":
            close = _find_block_close(tokens, i, "list_item_close")
            item_content = _walk_blocks(tokens, i + 1, close)
            if not item_content:
                item_content = [{"type": "paragraph", "content": []}]
            out.append({"type": "listItem", "content": item_content})
            i = close + 1
        elif ttype == "blockquote_open":
            close = _find_block_close(tokens, i, "blockquote_close")
            out.append({"type": "blockquote", "content": _walk_blocks(tokens, i + 1, close)})
            i = close + 1
        elif ttype == "fence" or ttype == "code_block":
            lang = (tok.info or "").strip() if ttype == "fence" else ""
            text = (tok.content or "").rstrip("\n")
            node: dict = {"type": "codeBlock"}
            if lang:
                node["attrs"] = {"language": lang}
            node["content"] = [{"type": "text", "text": text}] if text else []
            out.append(node)
            i += 1
        elif ttype == "hr":
            out.append({"type": "rule"})
            i += 1
        elif ttype == "table_open":
            close = _find_block_close(tokens, i, "table_close")
            out.append({
                "type": "table",
                "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
                "content": _walk_table(tokens, i + 1, close),
            })
            i = close + 1
        else:
            i += 1
    return out


def _walk_table(tokens: list, start: int, end: int) -> list[dict]:
    rows: list[dict] = []
    i = start
    while i < end:
        tok = tokens[i]
        if tok.type == "tr_open":
            close = _find_block_close(tokens, i, "tr_close")
            rows.append({"type": "tableRow", "content": _walk_table_row(tokens, i + 1, close)})
            i = close + 1
        else:
            i += 1
    return rows


def _walk_table_row(tokens: list, start: int, end: int) -> list[dict]:
    cells: list[dict] = []
    i = start
    while i < end:
        tok = tokens[i]
        if tok.type in ("th_open", "td_open"):
            close_type = "th_close" if tok.type == "th_open" else "td_close"
            close = _find_block_close(tokens, i, close_type)
            inline = tokens[i + 1] if i + 1 < close else None
            children = inline.children if (inline and inline.type == "inline") else []
            cell_type = "tableHeader" if tok.type == "th_open" else "tableCell"
            cells.append({
                "type": cell_type,
                "attrs": {},
                "content": [{"type": "paragraph", "content": _walk_inline(children or [])}],
            })
            i = close + 1
        else:
            i += 1
    return cells


def _find_inline_close(children: list, open_idx: int, open_type: str, close_type: str) -> int:
    depth = 1
    for j in range(open_idx + 1, len(children)):
        if children[j].type == open_type:
            depth += 1
        elif children[j].type == close_type:
            depth -= 1
            if depth == 0:
                return j
    return len(children)


def _walk_inline(children: list, marks: list[dict] | None = None) -> list[dict]:
    out: list[dict] = []
    marks = marks or []
    i = 0
    while i < len(children):
        tok = children[i]
        ttype = tok.type
        if ttype == "text":
            if tok.content:
                node: dict = {"type": "text", "text": tok.content}
                if marks:
                    node["marks"] = list(marks)
                out.append(node)
            i += 1
        elif ttype == "softbreak":
            out.append({"type": "text", "text": " "})
            i += 1
        elif ttype == "hardbreak":
            out.append({"type": "hardBreak"})
            i += 1
        elif ttype == "code_inline":
            if tok.content:
                out.append({
                    "type": "text",
                    "text": tok.content,
                    "marks": marks + [{"type": "code"}],
                })
            i += 1
        elif ttype == "strong_open":
            close = _find_inline_close(children, i, "strong_open", "strong_close")
            out.extend(_walk_inline(children[i + 1:close], marks + [{"type": "strong"}]))
            i = close + 1
        elif ttype == "em_open":
            close = _find_inline_close(children, i, "em_open", "em_close")
            out.extend(_walk_inline(children[i + 1:close], marks + [{"type": "em"}]))
            i = close + 1
        elif ttype == "s_open":
            close = _find_inline_close(children, i, "s_open", "s_close")
            out.extend(_walk_inline(children[i + 1:close], marks + [{"type": "strike"}]))
            i = close + 1
        elif ttype == "link_open":
            href = tok.attrGet("href") or ""
            close = _find_inline_close(children, i, "link_open", "link_close")
            link_mark = {"type": "link", "attrs": {"href": href}}
            out.extend(_walk_inline(children[i + 1:close], marks + [link_mark]))
            i = close + 1
        else:
            i += 1
    return out


# ── Tools ──────────────────────────────────────────────────────


@mcp.tool()
async def get_issue(
    jira_token: str,
    jira_email: str,
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
    result = await _request(
        "GET",
        f"/rest/api/3/issue/{issue_key}",
        email=jira_email,
        token=jira_token,
        params=params or None,
    )
    return _result(result)


@mcp.tool()
async def create_issue(
    jira_token: str,
    jira_email: str,
    project: str,
    summary: str,
    description: str = "",
    issue_type: str = "Task",
    priority: str | None = None,
    assignee_account_id: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Create a new Jira issue.

    `project` is the project key (e.g. 'PROJ'). `description` is markdown and
    is converted to ADF. `priority` is optional — many projects don't expose
    a priority field. `assignee_account_id` is the Atlassian accountId; use
    `find_user` to look it up by email or name.
    """
    fields: dict = {
        "project": {"key": project},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = _md_to_adf(description)
    if priority:
        fields["priority"] = {"name": priority}
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}
    if labels:
        fields["labels"] = labels
    result = await _request(
        "POST",
        "/rest/api/3/issue",
        email=jira_email,
        token=jira_token,
        json_body={"fields": fields},
    )
    return _result(result)


@mcp.tool()
async def update_issue(
    jira_token: str,
    jira_email: str,
    issue_key: str,
    summary: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    assignee_account_id: str | None = None,
    labels: list[str] | None = None,
) -> str:
    """Update fields on an existing Jira issue. Only the fields you set are sent.

    `description` is markdown. Pass an empty string for `assignee_account_id`
    to unassign.
    """
    fields: dict = {}
    if summary is not None:
        fields["summary"] = summary
    if description is not None:
        fields["description"] = _md_to_adf(description)
    if priority is not None:
        fields["priority"] = {"name": priority}
    if assignee_account_id is not None:
        fields["assignee"] = {"accountId": assignee_account_id} if assignee_account_id else None
    if labels is not None:
        fields["labels"] = labels
    if not fields:
        return "ERROR: no fields provided to update"
    result = await _request(
        "PUT",
        f"/rest/api/3/issue/{issue_key}",
        email=jira_email,
        token=jira_token,
        json_body={"fields": fields},
    )
    if isinstance(result, str):
        return result
    return f"Issue {issue_key} updated."


@mcp.tool()
async def delete_issue(jira_token: str, jira_email: str, issue_key: str) -> str:
    """Delete a Jira issue. This is permanent — use with care."""
    result = await _request(
        "DELETE",
        f"/rest/api/3/issue/{issue_key}",
        email=jira_email,
        token=jira_token,
    )
    if isinstance(result, str):
        return result
    return f"Issue {issue_key} deleted."


@mcp.tool()
async def get_transitions(jira_token: str, jira_email: str, issue_key: str) -> str:
    """List the workflow transitions currently available for an issue.

    Returns [{id, name, to:{name}}, ...]. Pass the `name` to `transition_issue`.
    """
    result = await _request(
        "GET",
        f"/rest/api/3/issue/{issue_key}/transitions",
        email=jira_email,
        token=jira_token,
    )
    if isinstance(result, str):
        return result
    transitions = result.get("transitions", []) if isinstance(result, dict) else []
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
    jira_email: str,
    issue_key: str,
    transition: str,
    comment: str = "",
) -> str:
    """Move an issue to a different status (e.g. 'In Progress', 'Done').

    `transition` is the human-readable transition name. Internally we look up
    the available transitions for this issue and resolve the matching id —
    Jira's API requires the id, not the name. Optional `comment` is markdown.
    """
    tres = await _request(
        "GET",
        f"/rest/api/3/issue/{issue_key}/transitions",
        email=jira_email,
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
        body["update"] = {"comment": [{"add": {"body": _md_to_adf(comment)}}]}
    result = await _request(
        "POST",
        f"/rest/api/3/issue/{issue_key}/transitions",
        email=jira_email,
        token=jira_token,
        json_body=body,
    )
    if isinstance(result, str):
        return result
    return f"Issue {issue_key} transitioned to '{transition}'."


@mcp.tool()
async def add_comment(
    jira_token: str,
    jira_email: str,
    issue_key: str,
    body: str,
) -> str:
    """Add a comment to a Jira issue. `body` is markdown."""
    result = await _request(
        "POST",
        f"/rest/api/3/issue/{issue_key}/comment",
        email=jira_email,
        token=jira_token,
        json_body={"body": _md_to_adf(body)},
    )
    return _result(result)


@mcp.tool()
async def search_issues(
    jira_token: str,
    jira_email: str,
    jql: str,
    max_results: int = 20,
    fields: list[str] | None = None,
    next_page_token: str | None = None,
) -> str:
    """Search for issues using JQL (Jira Query Language).

    Uses the new POST /rest/api/3/search/jql endpoint. Returns
    {issues, nextPageToken?}. There is no `total` — Atlassian removed it from
    this endpoint. To paginate, pass the returned `nextPageToken` back in.
    """
    body: dict = {"jql": jql, "maxResults": max_results}
    if fields:
        body["fields"] = fields
    if next_page_token:
        body["nextPageToken"] = next_page_token
    result = await _request(
        "POST",
        "/rest/api/3/search/jql",
        email=jira_email,
        token=jira_token,
        json_body=body,
    )
    return _result(result)


@mcp.tool()
async def assign_issue(
    jira_token: str,
    jira_email: str,
    issue_key: str,
    account_id: str | None,
) -> str:
    """Assign a Jira issue to a user by accountId.

    Use `find_user` to resolve email/name → accountId. Pass an empty string or
    null `account_id` to unassign.
    """
    payload = {"accountId": account_id if account_id else None}
    result = await _request(
        "PUT",
        f"/rest/api/3/issue/{issue_key}/assignee",
        email=jira_email,
        token=jira_token,
        json_body=payload,
    )
    if isinstance(result, str):
        return result
    return f"Issue {issue_key} assignee updated."


@mcp.tool()
async def find_user(jira_token: str, jira_email: str, query: str) -> str:
    """Find Jira users by display name or email.

    Returns [{accountId, displayName, emailAddress}]. Use the accountId with
    `assign_issue` or `create_issue`.
    """
    result = await _request(
        "GET",
        "/rest/api/3/user/search",
        email=jira_email,
        token=jira_token,
        params={"query": query},
    )
    if isinstance(result, str):
        return result
    users = result if isinstance(result, list) else []
    return json.dumps([
        {
            "accountId": u.get("accountId"),
            "displayName": u.get("displayName"),
            "emailAddress": u.get("emailAddress"),
        }
        for u in users
        if isinstance(u, dict)
    ])


@mcp.tool()
async def link_issues(
    jira_token: str,
    jira_email: str,
    inward_issue: str,
    outward_issue: str,
    link_type: str,
) -> str:
    """Create a link between two issues.

    `link_type` is the link type name as configured in Jira (e.g. 'Blocks',
    'Relates', 'Duplicate', 'Cloners').
    """
    body = {
        "type": {"name": link_type},
        "inwardIssue": {"key": inward_issue},
        "outwardIssue": {"key": outward_issue},
    }
    result = await _request(
        "POST",
        "/rest/api/3/issueLink",
        email=jira_email,
        token=jira_token,
        json_body=body,
    )
    if isinstance(result, str):
        return result
    return f"Link created: {inward_issue} {link_type} {outward_issue}."


@mcp.tool()
async def list_sprints(
    jira_token: str,
    jira_email: str,
    board_id: int,
    state: str = "active",
) -> str:
    """List sprints on a Jira board.

    `state` is one of 'active', 'closed', 'future', or comma-separated.
    """
    result = await _request(
        "GET",
        f"/rest/agile/1.0/board/{board_id}/sprint",
        email=jira_email,
        token=jira_token,
        params={"state": state},
    )
    return _result(result)


@mcp.tool()
async def get_sprint_issues(
    jira_token: str,
    jira_email: str,
    sprint_id: int,
    status: str | None = None,
) -> str:
    """Get all issues in a sprint. Optional `status` filters by issue status name."""
    params: dict = {}
    if status:
        params["jql"] = f'status = "{status}"'
    result = await _request(
        "GET",
        f"/rest/agile/1.0/sprint/{sprint_id}/issue",
        email=jira_email,
        token=jira_token,
        params=params or None,
    )
    return _result(result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

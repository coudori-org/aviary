"""Confluence MCP Server.

Real Confluence Cloud REST API v2 integration (with a couple of v1 fallbacks
for endpoints that don't exist in v2 yet).

Auth: HTTP Basic with email + API token, both injected by the MCP Gateway as
the `confluence_email` / `confluence_token` arguments. The site URL comes from
the CONFLUENCE_BASE_URL env var (shared corporate Atlassian instance).

Page bodies accept markdown — `_md_to_storage` converts them to Confluence
storage XHTML so tables, code blocks, lists, and inline formatting render
correctly. Code blocks are wrapped in <ac:structured-macro ac:name="code">
which is Confluence's native code block.
"""

import base64
import html
import json
import os
import re
from typing import Any

import httpx
from markdown_it import MarkdownIt
from mcp.server.fastmcp import FastMCP

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")

mcp = FastMCP("confluence", host="0.0.0.0", port=8000, stateless_http=True)


# ── HTTP plumbing ──────────────────────────────────────────────

_http_client: httpx.AsyncClient | None = None


def _client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=CONFLUENCE_BASE_URL, timeout=30.0)
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
    """Issue an authenticated Confluence API request.

    Returns parsed JSON on 2xx, or an "ERROR: ..." string on failure. Tools
    propagate that string as their return value.
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
    if isinstance(value, str):
        return value
    return json.dumps(value)


# ── Markdown → Confluence storage format ───────────────────────

_md = MarkdownIt("commonmark").enable("table").enable("strikethrough")

_FENCE_RE = re.compile(
    r'<pre><code(?: class="language-([^"]+)")?>(.*?)</code></pre>',
    re.DOTALL,
)


def _replace_fence(m: re.Match) -> str:
    lang = m.group(1) or ""
    code = html.unescape(m.group(2) or "")
    code = code.rstrip("\n")
    # CDATA can't contain "]]>"
    code = code.replace("]]>", "]]]]><![CDATA[>")
    parts = ['<ac:structured-macro ac:name="code">']
    if lang:
        parts.append(f'<ac:parameter ac:name="language">{lang}</ac:parameter>')
    parts.append(f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>')
    parts.append("</ac:structured-macro>")
    return "".join(parts)


def _md_to_storage(md: str) -> str:
    """Convert markdown to Confluence storage format (XHTML).

    Standard markdown → HTML via markdown-it-py (CommonMark + GFM tables +
    strikethrough), then post-processed to wrap fenced code blocks in
    Confluence's native <ac:structured-macro ac:name="code"> macro.

    If the input already starts with '<' (after stripping whitespace) it is
    treated as raw storage XML and passed through unchanged — letting power
    users hand-write storage when they need macros the converter doesn't know
    about.
    """
    if not md:
        return ""
    if md.lstrip().startswith("<"):
        return md
    html_out = _md.render(md)
    return _FENCE_RE.sub(_replace_fence, html_out)


# ── Internal helpers ───────────────────────────────────────────


async def _resolve_space_id(space_key: str, *, email: str, token: str) -> str:
    """Return the numeric space id for a space key, or an ERROR string.

    v2's GET /spaces/{id} requires a numeric id, but humans use space keys —
    so we look up via the list endpoint with `keys=` filter.
    """
    result = await _request(
        "GET",
        "/wiki/api/v2/spaces",
        email=email,
        token=token,
        params={"keys": space_key},
    )
    if isinstance(result, str):
        return result
    spaces = result.get("results", []) if isinstance(result, dict) else []
    if not spaces:
        return f"ERROR: space key '{space_key}' not found"
    return str(spaces[0].get("id"))


# ── Tools ──────────────────────────────────────────────────────


@mcp.tool()
async def get_page(
    confluence_token: str,
    confluence_email: str,
    page_id: str | None = None,
    space_key: str | None = None,
    title: str | None = None,
) -> str:
    """Get a Confluence page by id, or by (space_key, title).

    When `page_id` is given, fetches that page directly. Otherwise resolves
    `space_key` → space-id and looks up the page by exact title within that
    space. The body is returned in storage format.
    """
    if page_id:
        result = await _request(
            "GET",
            f"/wiki/api/v2/pages/{page_id}",
            email=confluence_email,
            token=confluence_token,
            params={"body-format": "storage"},
        )
        return _result(result)
    if not (space_key and title):
        return "ERROR: provide either page_id, or both space_key and title"
    space_id = await _resolve_space_id(
        space_key, email=confluence_email, token=confluence_token
    )
    if space_id.startswith("ERROR"):
        return space_id
    result = await _request(
        "GET",
        "/wiki/api/v2/pages",
        email=confluence_email,
        token=confluence_token,
        params={"space-id": space_id, "title": title, "body-format": "storage"},
    )
    if isinstance(result, str):
        return result
    pages = result.get("results", []) if isinstance(result, dict) else []
    if not pages:
        return f"ERROR: no page found with title '{title}' in space '{space_key}'"
    return json.dumps(pages[0])


@mcp.tool()
async def create_page(
    confluence_token: str,
    confluence_email: str,
    space_key: str,
    title: str,
    body: str,
    parent_id: str | None = None,
) -> str:
    """Create a new Confluence page. `body` is markdown.

    `space_key` is the human-readable key (e.g. 'ENG'); we resolve it to the
    numeric spaceId v2 requires. `parent_id` is optional — when omitted the
    page is created at the root of the space.
    """
    space_id = await _resolve_space_id(
        space_key, email=confluence_email, token=confluence_token
    )
    if space_id.startswith("ERROR"):
        return space_id
    payload: dict = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {"representation": "storage", "value": _md_to_storage(body)},
    }
    if parent_id:
        payload["parentId"] = parent_id
    result = await _request(
        "POST",
        "/wiki/api/v2/pages",
        email=confluence_email,
        token=confluence_token,
        json_body=payload,
    )
    return _result(result)


@mcp.tool()
async def update_page(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    body: str,
    title: str | None = None,
    version_comment: str | None = None,
) -> str:
    """Update an existing Confluence page. `body` is markdown.

    Confluence requires the next version number for optimistic locking, so we
    fetch the current page first to read its version. If `title` isn't given,
    we reuse the current title (v2 PUT requires a title).
    """
    current = await _request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}",
        email=confluence_email,
        token=confluence_token,
    )
    if isinstance(current, str):
        return current
    current_version = (current.get("version") or {}).get("number") or 1
    payload: dict = {
        "id": page_id,
        "status": "current",
        "title": title or current.get("title", ""),
        "body": {"representation": "storage", "value": _md_to_storage(body)},
        "version": {"number": current_version + 1},
    }
    if version_comment:
        payload["version"]["message"] = version_comment
    result = await _request(
        "PUT",
        f"/wiki/api/v2/pages/{page_id}",
        email=confluence_email,
        token=confluence_token,
        json_body=payload,
    )
    return _result(result)


@mcp.tool()
async def delete_page(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    purge: bool = False,
) -> str:
    """Delete (trash) a Confluence page. Pass `purge=true` to permanently delete."""
    params = {"purge": "true"} if purge else None
    result = await _request(
        "DELETE",
        f"/wiki/api/v2/pages/{page_id}",
        email=confluence_email,
        token=confluence_token,
        params=params,
    )
    if isinstance(result, str):
        return result
    return f"Page {page_id} deleted."


@mcp.tool()
async def search(
    confluence_token: str,
    confluence_email: str,
    cql: str,
    limit: int = 20,
) -> str:
    """Search Confluence content using CQL (Confluence Query Language).

    Uses the v1 /wiki/rest/api/search endpoint — Confluence v2 does not yet
    expose a CQL search.
    """
    result = await _request(
        "GET",
        "/wiki/rest/api/search",
        email=confluence_email,
        token=confluence_token,
        params={"cql": cql, "limit": limit},
    )
    return _result(result)


@mcp.tool()
async def get_child_pages(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    limit: int = 25,
) -> str:
    """List the direct child pages of a Confluence page."""
    result = await _request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}/children",
        email=confluence_email,
        token=confluence_token,
        params={"limit": limit},
    )
    return _result(result)


@mcp.tool()
async def list_spaces(
    confluence_token: str,
    confluence_email: str,
    type: str | None = None,
    limit: int = 25,
) -> str:
    """List Confluence spaces. Optional `type` filters by 'global' or 'personal'."""
    params: dict = {"limit": limit}
    if type:
        params["type"] = type
    result = await _request(
        "GET",
        "/wiki/api/v2/spaces",
        email=confluence_email,
        token=confluence_token,
        params=params,
    )
    return _result(result)


@mcp.tool()
async def get_space(
    confluence_token: str,
    confluence_email: str,
    space_key: str,
) -> str:
    """Get details of a Confluence space by its key (e.g. 'ENG')."""
    result = await _request(
        "GET",
        "/wiki/api/v2/spaces",
        email=confluence_email,
        token=confluence_token,
        params={"keys": space_key},
    )
    if isinstance(result, str):
        return result
    spaces = result.get("results", []) if isinstance(result, dict) else []
    if not spaces:
        return f"ERROR: space key '{space_key}' not found"
    return json.dumps(spaces[0])


@mcp.tool()
async def add_label(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    label: str,
) -> str:
    """Add a label to a Confluence page.

    Uses the v1 endpoint /wiki/rest/api/content/{id}/label — Confluence v2
    labels are read-only.
    """
    result = await _request(
        "POST",
        f"/wiki/rest/api/content/{page_id}/label",
        email=confluence_email,
        token=confluence_token,
        json_body=[{"prefix": "global", "name": label}],
    )
    if isinstance(result, str):
        return result
    return f"Label '{label}' added to page {page_id}."


@mcp.tool()
async def get_page_history(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    limit: int = 10,
) -> str:
    """Get version history of a Confluence page."""
    result = await _request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}/versions",
        email=confluence_email,
        token=confluence_token,
        params={"limit": limit},
    )
    return _result(result)


@mcp.tool()
async def add_comment(
    confluence_token: str,
    confluence_email: str,
    page_id: str,
    body: str,
) -> str:
    """Add a footer comment to a Confluence page. `body` is markdown."""
    payload = {
        "pageId": page_id,
        "body": {"representation": "storage", "value": _md_to_storage(body)},
    }
    result = await _request(
        "POST",
        "/wiki/api/v2/footer-comments",
        email=confluence_email,
        token=confluence_token,
        json_body=payload,
    )
    return _result(result)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

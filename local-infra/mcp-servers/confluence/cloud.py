"""Confluence Cloud MCP tools — REST API v2 (with two v1 fallbacks)."""

import json

from mcp.server.fastmcp import FastMCP

from common import md_to_storage, request, result

mcp = FastMCP("confluence", host="0.0.0.0", port=8000, stateless_http=True)


async def _resolve_space_id(space_key: str, *, token: str) -> str:
    # v2 endpoints want numeric spaceId; users pass keys.
    res = await request(
        "GET",
        "/wiki/api/v2/spaces",
        token=token,
        params={"keys": space_key},
    )
    if isinstance(res, str):
        return res
    spaces = res.get("results", []) if isinstance(res, dict) else []
    if not spaces:
        return f"ERROR: space key '{space_key}' not found"
    return str(spaces[0].get("id"))


@mcp.tool()
async def get_page(
    confluence_token: str,
    page_id: str | int | None = None,
    space_key: str | None = None,
    title: str | None = None,
) -> str:
    """Get a Confluence page by id, or by (space_key, title).

    When `page_id` is given, fetches that page directly. Otherwise resolves
    `space_key` → space-id and looks up the page by exact title within that
    space. The body is returned in storage format.
    """
    if page_id is not None:
        page_id = str(page_id)
    if page_id:
        res = await request(
            "GET",
            f"/wiki/api/v2/pages/{page_id}",
            token=confluence_token,
            params={"body-format": "storage"},
        )
        return result(res)
    if not (space_key and title):
        return "ERROR: provide either page_id, or both space_key and title"
    space_id = await _resolve_space_id(space_key, token=confluence_token)
    if space_id.startswith("ERROR"):
        return space_id
    res = await request(
        "GET",
        "/wiki/api/v2/pages",
        token=confluence_token,
        params={"space-id": space_id, "title": title, "body-format": "storage"},
    )
    if isinstance(res, str):
        return res
    pages = res.get("results", []) if isinstance(res, dict) else []
    if not pages:
        return f"ERROR: no page found with title '{title}' in space '{space_key}'"
    return json.dumps(pages[0])


@mcp.tool()
async def create_page(
    confluence_token: str,
    space_key: str,
    title: str,
    body: str,
    parent_id: str | int | None = None,
) -> str:
    """Create a new Confluence page. `body` is markdown.

    `space_key` is the human-readable key (e.g. 'ENG'); we resolve it to the
    numeric spaceId v2 requires. `parent_id` is optional — when omitted the
    page is created at the root of the space.
    """
    if parent_id is not None:
        parent_id = str(parent_id)
    space_id = await _resolve_space_id(space_key, token=confluence_token)
    if space_id.startswith("ERROR"):
        return space_id
    payload: dict = {
        "spaceId": space_id,
        "status": "current",
        "title": title,
        "body": {"representation": "storage", "value": md_to_storage(body)},
    }
    if parent_id:
        payload["parentId"] = parent_id
    res = await request(
        "POST",
        "/wiki/api/v2/pages",
        token=confluence_token,
        json_body=payload,
    )
    return result(res)


@mcp.tool()
async def update_page(
    confluence_token: str,
    page_id: str | int,
    body: str,
    title: str | None = None,
    version_comment: str | None = None,
) -> str:
    """Update an existing Confluence page. `body` is markdown.

    Confluence requires the next version number for optimistic locking, so we
    fetch the current page first to read its version. If `title` isn't given,
    we reuse the current title (v2 PUT requires a title).
    """
    page_id = str(page_id)
    current = await request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}",
        token=confluence_token,
    )
    if isinstance(current, str):
        return current
    current_version = (current.get("version") or {}).get("number") or 1
    payload: dict = {
        "id": page_id,
        "status": "current",
        "title": title or current.get("title", ""),
        "body": {"representation": "storage", "value": md_to_storage(body)},
        "version": {"number": current_version + 1},
    }
    if version_comment:
        payload["version"]["message"] = version_comment
    res = await request(
        "PUT",
        f"/wiki/api/v2/pages/{page_id}",
        token=confluence_token,
        json_body=payload,
    )
    return result(res)


@mcp.tool()
async def delete_page(
    confluence_token: str,
    page_id: str | int,
    purge: bool = False,
) -> str:
    """Delete (trash) a Confluence page. Pass `purge=true` to permanently delete."""
    page_id = str(page_id)
    params = {"purge": "true"} if purge else None
    res = await request(
        "DELETE",
        f"/wiki/api/v2/pages/{page_id}",
        token=confluence_token,
        params=params,
    )
    if isinstance(res, str):
        return res
    return f"Page {page_id} deleted."


@mcp.tool()
async def search(
    confluence_token: str,
    cql: str,
    limit: int = 20,
) -> str:
    """Search Confluence content using CQL (Confluence Query Language).

    Uses the v1 /wiki/rest/api/search endpoint — Confluence v2 does not yet
    expose a CQL search.
    """
    res = await request(
        "GET",
        "/wiki/rest/api/search",
        token=confluence_token,
        params={"cql": cql, "limit": limit},
    )
    return result(res)


@mcp.tool()
async def get_child_pages(
    confluence_token: str,
    page_id: str | int,
    limit: int = 25,
) -> str:
    """List the direct child pages of a Confluence page."""
    page_id = str(page_id)
    res = await request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}/children",
        token=confluence_token,
        params={"limit": limit},
    )
    return result(res)


@mcp.tool()
async def list_spaces(
    confluence_token: str,
    type: str | None = None,
    limit: int = 25,
) -> str:
    """List Confluence spaces. Optional `type` filters by 'global' or 'personal'."""
    params: dict = {"limit": limit}
    if type:
        params["type"] = type
    res = await request(
        "GET",
        "/wiki/api/v2/spaces",
        token=confluence_token,
        params=params,
    )
    return result(res)


@mcp.tool()
async def get_space(
    confluence_token: str,
    space_key: str,
) -> str:
    """Get details of a Confluence space by its key (e.g. 'ENG')."""
    res = await request(
        "GET",
        "/wiki/api/v2/spaces",
        token=confluence_token,
        params={"keys": space_key},
    )
    if isinstance(res, str):
        return res
    spaces = res.get("results", []) if isinstance(res, dict) else []
    if not spaces:
        return f"ERROR: space key '{space_key}' not found"
    return json.dumps(spaces[0])


@mcp.tool()
async def add_label(
    confluence_token: str,
    page_id: str | int,
    label: str,
) -> str:
    """Add a label to a Confluence page.

    Uses the v1 endpoint /wiki/rest/api/content/{id}/label — Confluence v2
    labels are read-only.
    """
    page_id = str(page_id)
    res = await request(
        "POST",
        f"/wiki/rest/api/content/{page_id}/label",
        token=confluence_token,
        json_body=[{"prefix": "global", "name": label}],
    )
    if isinstance(res, str):
        return res
    return f"Label '{label}' added to page {page_id}."


@mcp.tool()
async def get_page_history(
    confluence_token: str,
    page_id: str | int,
    limit: int = 10,
) -> str:
    """Get version history of a Confluence page."""
    page_id = str(page_id)
    res = await request(
        "GET",
        f"/wiki/api/v2/pages/{page_id}/versions",
        token=confluence_token,
        params={"limit": limit},
    )
    return result(res)


@mcp.tool()
async def add_comment(
    confluence_token: str,
    page_id: str | int,
    body: str,
) -> str:
    """Add a footer comment to a Confluence page. `body` is markdown."""
    page_id = str(page_id)
    payload = {
        "pageId": page_id,
        "body": {"representation": "storage", "value": md_to_storage(body)},
    }
    res = await request(
        "POST",
        "/wiki/api/v2/footer-comments",
        token=confluence_token,
        json_body=payload,
    )
    return result(res)

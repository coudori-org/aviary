"""Confluence legacy MCP tools — REST API v1 (Server / Data Center).

Cloud-parity quirks worth knowing:
  - Pages/comments/labels share /rest/api/content with a `type` discriminator.
  - Spaces are addressed by key directly — no numeric-id resolver needed.
  - History is fetched via /rest/api/content/{id}/history.
"""

import json

from mcp.server.fastmcp import FastMCP

from common import md_to_storage, request, result

mcp = FastMCP("confluence", host="0.0.0.0", port=8000, stateless_http=True)


@mcp.tool()
async def get_page(
    confluence_token: str,
    page_id: str | int | None = None,
    space_key: str | None = None,
    title: str | None = None,
) -> str:
    """Get a Confluence page by id, or by (space_key, title).

    Body is returned in storage format (`expand=body.storage,version`).
    """
    if page_id is not None:
        page_id = str(page_id)
    if page_id:
        res = await request(
            "GET",
            f"/rest/api/content/{page_id}",
            token=confluence_token,
            params={"expand": "body.storage,version"},
        )
        return result(res)
    if not (space_key and title):
        return "ERROR: provide either page_id, or both space_key and title"
    res = await request(
        "GET",
        "/rest/api/content",
        token=confluence_token,
        params={
            "spaceKey": space_key,
            "title": title,
            "expand": "body.storage,version",
        },
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

    `parent_id` is optional; when given the page is added as a child via the
    `ancestors` array, otherwise it sits at the root of the space.
    """
    payload: dict = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "body": {
            "storage": {"value": md_to_storage(body), "representation": "storage"}
        },
    }
    if parent_id is not None:
        payload["ancestors"] = [{"id": str(parent_id)}]
    res = await request(
        "POST",
        "/rest/api/content",
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
    fetch the current page first to read its version + title.
    """
    page_id = str(page_id)
    current = await request(
        "GET",
        f"/rest/api/content/{page_id}",
        token=confluence_token,
        params={"expand": "version"},
    )
    if isinstance(current, str):
        return current
    current_version = (current.get("version") or {}).get("number") or 1
    payload: dict = {
        "type": "page",
        "title": title or current.get("title", ""),
        "body": {
            "storage": {"value": md_to_storage(body), "representation": "storage"}
        },
        "version": {"number": current_version + 1},
    }
    if version_comment:
        payload["version"]["message"] = version_comment
    res = await request(
        "PUT",
        f"/rest/api/content/{page_id}",
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
    """Delete (trash) a Confluence page. Pass `purge=true` to permanently delete.

    On Server / DC permanent purge requires deleting the trashed page again
    with `?status=trashed`.
    """
    page_id = str(page_id)
    params = {"status": "trashed"} if purge else None
    res = await request(
        "DELETE",
        f"/rest/api/content/{page_id}",
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
    """Search Confluence content using CQL (Confluence Query Language)."""
    res = await request(
        "GET",
        "/rest/api/search",
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
        f"/rest/api/content/{page_id}/child/page",
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
        "/rest/api/space",
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
        f"/rest/api/space/{space_key}",
        token=confluence_token,
    )
    return result(res)


@mcp.tool()
async def add_label(
    confluence_token: str,
    page_id: str | int,
    label: str,
) -> str:
    """Add a label to a Confluence page."""
    page_id = str(page_id)
    res = await request(
        "POST",
        f"/rest/api/content/{page_id}/label",
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
    """Get version history of a Confluence page.

    Server v1 exposes a single history record (creation + last-updated) at
    /rest/api/content/{id}/history; expanding `previousVersion`/`nextVersion`
    lets the caller walk versions one hop at a time. `limit` is accepted for
    interface parity with the cloud variant but ignored — the endpoint
    returns a single record.
    """
    page_id = str(page_id)
    res = await request(
        "GET",
        f"/rest/api/content/{page_id}/history",
        token=confluence_token,
        params={"expand": "lastUpdated,previousVersion,nextVersion,contributors"},
    )
    return result(res)


@mcp.tool()
async def add_comment(
    confluence_token: str,
    page_id: str | int,
    body: str,
) -> str:
    """Add a comment to a Confluence page. `body` is markdown."""
    page_id = str(page_id)
    payload = {
        "type": "comment",
        "container": {"id": str(page_id), "type": "page"},
        "body": {
            "storage": {"value": md_to_storage(body), "representation": "storage"}
        },
    }
    res = await request(
        "POST",
        "/rest/api/content",
        token=confluence_token,
        json_body=payload,
    )
    return result(res)

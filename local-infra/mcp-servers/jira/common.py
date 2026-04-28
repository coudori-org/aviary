"""HTTP plumbing for the Jira MCP server (cloud + legacy)."""

import base64
import json
import logging
import os
from typing import Any

import httpx

logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("mcp").setLevel(logging.WARNING)

JIRA_BASE_URL = os.environ["JIRA_BASE_URL"].rstrip("/")
_VARIANT = os.environ.get("JIRA_API_VARIANT", "cloud").lower()


_http_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=JIRA_BASE_URL, timeout=30.0)
    return _http_client


def auth_header(token: str) -> str:
    # legacy = Server/DC PAT (Bearer); cloud = `{email}:{api-token}` (Basic).
    if _VARIANT == "legacy":
        return f"Bearer {token}"
    raw = token.encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


async def request(
    method: str,
    path: str,
    *,
    token: str,
    json_body: Any = None,
    params: dict | None = None,
) -> dict | list | str:
    # Returns parsed JSON on 2xx, "ERROR: ..." string on failure (tools
    # propagate the string so the agent sees a readable error).
    headers = {
        "Authorization": auth_header(token),
        "Accept": "application/json",
    }
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    try:
        resp = await client().request(
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


def result(value: dict | list | str) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)

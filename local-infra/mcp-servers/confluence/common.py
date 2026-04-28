"""HTTP plumbing + markdown→storage converter for the Confluence MCP server."""

import base64
import html
import json
import logging
import os
import re
from typing import Any

import httpx
from markdown_it import MarkdownIt

logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("mcp").setLevel(logging.WARNING)

CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"].rstrip("/")
_VARIANT = os.environ.get("CONFLUENCE_API_VARIANT", "cloud").lower()


_http_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=CONFLUENCE_BASE_URL, timeout=30.0)
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


_md = MarkdownIt("commonmark").enable("table").enable("strikethrough")

_FENCE_RE = re.compile(
    r'<pre><code(?: class="language-([^"]+)")?>(.*?)</code></pre>',
    re.DOTALL,
)


def _replace_fence(m: re.Match) -> str:
    lang = m.group(1) or ""
    code = html.unescape(m.group(2) or "")
    code = code.rstrip("\n")
    # CDATA can't contain "]]>".
    code = code.replace("]]>", "]]]]><![CDATA[>")
    parts = ['<ac:structured-macro ac:name="code">']
    if lang:
        parts.append(f'<ac:parameter ac:name="language">{lang}</ac:parameter>')
    parts.append(f'<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>')
    parts.append("</ac:structured-macro>")
    return "".join(parts)


def md_to_storage(md: str) -> str:
    # Input starting with '<' is treated as raw storage XML and passed through.
    if not md:
        return ""
    if md.lstrip().startswith("<"):
        return md
    html_out = _md.render(md)
    return _FENCE_RE.sub(_replace_fence, html_out)

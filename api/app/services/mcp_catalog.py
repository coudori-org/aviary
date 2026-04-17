"""Shared MCP catalog fetcher.

LiteLLM owns all visibility/ACL decisions. We open an MCP session to
``/mcp`` with the caller's OIDC JWT and relay whatever LiteLLM's
guardrail returns.
"""

from __future__ import annotations

import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def fetch_tools(user_token: str) -> list[dict]:
    """Return every MCP tool the caller is allowed to see.

    Each entry: ``{"name": "<server>__<tool>", "description": str | None,
    "inputSchema": dict}``.
    """
    base = os.environ["LITELLM_URL"].rstrip("/")
    async with streamablehttp_client(
        f"{base}/mcp", headers={"Authorization": f"Bearer {user_token}"},
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
    return [
        {
            "name": t.name,
            "description": getattr(t, "description", None),
            "inputSchema": getattr(t, "inputSchema", None) or {},
        }
        for t in result.tools
    ]

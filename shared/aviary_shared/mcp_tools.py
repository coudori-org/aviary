"""MCP tool catalog upsert shared by admin discovery and gateway startup."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool


async def upsert_tools(
    db: AsyncSession, server: McpServer, raw_tools: list[dict[str, Any]],
) -> tuple[int, int]:
    """Reconcile tool catalog. Returns (discovered, removed). Caller commits."""
    result = await db.execute(select(McpTool).where(McpTool.server_id == server.id))
    existing = {t.name: t for t in result.scalars().all()}

    discovered_names: set[str] = set()
    for raw in raw_tools:
        name = raw["name"]
        discovered_names.add(name)
        if name in existing:
            existing[name].description = raw.get("description", "")
            existing[name].input_schema = raw.get("inputSchema", {})
        else:
            db.add(McpTool(
                server_id=server.id,
                name=name,
                description=raw.get("description", ""),
                input_schema=raw.get("inputSchema", {}),
            ))

    removed = set(existing.keys()) - discovered_names
    for name in removed:
        await db.delete(existing[name])

    server.last_discovered_at = datetime.now(timezone.utc)
    server.status = "active"
    await db.flush()
    return len(raw_tools), len(removed)

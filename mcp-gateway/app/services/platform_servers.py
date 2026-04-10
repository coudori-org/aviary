"""Auto-register platform-provided MCP servers on startup.

Reads from a YAML config file and ensures each server exists in the DB
with is_platform_provided=True. Triggers tool discovery via MCP SDK client.
"""

import logging
from datetime import datetime, timezone

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpTool
from app.config import settings
from app.mcp.connection_pool import pool

logger = logging.getLogger(__name__)


def _load_platform_servers() -> list[dict]:
    """Load platform server definitions from YAML config."""
    config_path = settings.platform_servers_config
    try:
        with open(config_path) as f:
            servers = yaml.safe_load(f)
        if not isinstance(servers, list):
            raise ValueError(f"Expected a list in {config_path}")
        return servers
    except FileNotFoundError:
        logger.warning("Platform servers config not found: %s", config_path)
        return []


async def _discover_tools_for_server(db: AsyncSession, server: McpServer) -> int:
    """Connect to a backend MCP server via MCP SDK and populate tools in DB."""
    try:
        raw_tools = await pool.list_tools(server)
    except Exception:  # Best-effort: MCP SDK tool discovery can fail in many ways
        logger.warning("Failed to discover tools from %s — will retry on next startup", server.name)
        return 0

    result = await db.execute(
        select(McpTool).where(McpTool.server_id == server.id)
    )
    existing = {t.name: t for t in result.scalars().all()}

    discovered_names = set()
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

    for name in set(existing.keys()) - discovered_names:
        await db.delete(existing[name])

    server.last_discovered_at = datetime.now(timezone.utc)
    server.status = "active"

    return len(raw_tools)


async def register_platform_servers(db: AsyncSession) -> None:
    """Ensure all platform-provided MCP servers are registered in the DB."""
    platform_servers = _load_platform_servers()

    for spec in platform_servers:
        result = await db.execute(
            select(McpServer).where(McpServer.name == spec["name"])
        )
        server = result.scalar_one_or_none()

        if server is None:
            server = McpServer(
                name=spec["name"],
                description=spec["description"],
                transport_type=spec["transport_type"],
                connection_config=spec["connection_config"],
                tags=spec.get("tags", []),
                is_platform_provided=True,
                status="active",
            )
            db.add(server)
            await db.flush()
            logger.info("Registered platform MCP server: %s", spec["name"])
        else:
            server.connection_config = spec["connection_config"]
            server.description = spec["description"]
            server.tags = spec.get("tags", [])
            server.is_platform_provided = True
            await db.flush()

        count = await _discover_tools_for_server(db, server)
        if count > 0:
            logger.info("Discovered %d tools for %s", count, spec["name"])

    await db.commit()

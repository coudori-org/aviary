"""Register platform-provided MCP servers on startup."""

import logging

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer
from aviary_shared.mcp_tools import upsert_tools
from app.config import settings
from app.mcp.connection_pool import pool

logger = logging.getLogger(__name__)


def _load_platform_servers() -> list[dict]:
    """Missing file is fine; malformed file fails fast."""
    config_path = settings.platform_servers_config
    try:
        with open(config_path) as f:
            servers = yaml.safe_load(f)
    except FileNotFoundError:
        logger.info("No platform servers config at %s", config_path)
        return []
    if not isinstance(servers, list):
        raise ValueError(f"Expected a list in {config_path}, got {type(servers).__name__}")
    return servers


async def _discover_tools_for_server(db: AsyncSession, server: McpServer) -> int:
    """Discovery failure → server status='degraded'; other servers still register."""
    try:
        raw_tools = await pool.list_tools(server)
    except Exception:
        logger.exception("Failed to discover tools from %s", server.name)
        server.status = "degraded"
        return 0

    discovered, _ = await upsert_tools(db, server, raw_tools)
    return discovered


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

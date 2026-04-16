"""MCP tool access — simplified owner-only world.

Any authenticated user may discover and invoke any registered MCP tool.
Fine-grained RBAC returns alongside the broader redesign."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, User


async def check_tool_access(
    db: AsyncSession,
    user_external_id: str,
    server_id: uuid.UUID,
    tool_id: uuid.UUID | None = None,
) -> str | None:
    """Return 'use' for any authenticated user; None otherwise."""
    user = (await db.execute(
        select(User).where(User.external_id == user_external_id)
    )).scalar_one_or_none()
    if user is None:
        return None

    server = (await db.execute(
        select(McpServer).where(McpServer.id == server_id)
    )).scalar_one_or_none()
    if server is None:
        return None

    return "use"


async def get_accessible_servers(
    db: AsyncSession, user_external_id: str,
) -> list[uuid.UUID]:
    """Any authenticated user sees every active server."""
    user = (await db.execute(
        select(User).where(User.external_id == user_external_id)
    )).scalar_one_or_none()
    if user is None:
        return []
    result = await db.execute(select(McpServer.id))
    return list(result.scalars().all())

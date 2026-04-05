"""MCP tool ACL resolution — default-deny, user-based."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import McpServer, McpToolAcl, TeamMember, User


async def check_tool_access(
    db: AsyncSession,
    user_external_id: str,
    server_id: uuid.UUID,
    tool_id: uuid.UUID | None = None,
) -> str | None:
    """Check if user has access to a tool (or server).

    Returns the permission level ('use' or 'view') if granted, None if denied.

    Resolution order (default-deny, with platform-provided bypass):
    0. Platform-provided server → full access ('use') for all authenticated users
    1. Platform admin → full access ('use')
    2. Direct user ACL on specific tool
    3. Direct user ACL on server (tool_id IS NULL)
    4. Team ACL on specific tool (highest permission wins)
    5. Team ACL on server (highest permission wins)
    6. Deny (return None)
    """
    # 0. Platform-provided servers are accessible to all authenticated users
    result = await db.execute(select(McpServer).where(McpServer.id == server_id))
    server = result.scalar_one_or_none()
    if server and server.is_platform_provided:
        return "use"

    # Resolve internal user_id from external_id (OIDC sub)
    result = await db.execute(select(User).where(User.external_id == user_external_id))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    # 1. Platform admin
    if user.is_platform_admin:
        return "use"

    # 2. Direct user ACL on specific tool
    if tool_id is not None:
        result = await db.execute(
            select(McpToolAcl.permission).where(
                McpToolAcl.server_id == server_id,
                McpToolAcl.tool_id == tool_id,
                McpToolAcl.user_id == user.id,
            )
        )
        perm = result.scalar_one_or_none()
        if perm is not None:
            return perm

    # 3. Direct user ACL on server (tool_id IS NULL)
    result = await db.execute(
        select(McpToolAcl.permission).where(
            McpToolAcl.server_id == server_id,
            McpToolAcl.tool_id.is_(None),
            McpToolAcl.user_id == user.id,
        )
    )
    perm = result.scalar_one_or_none()
    if perm is not None:
        return perm

    # Get user's team IDs
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = list(result.scalars().all())
    if not team_ids:
        return None

    # 4. Team ACL on specific tool
    if tool_id is not None:
        result = await db.execute(
            select(McpToolAcl.permission).where(
                McpToolAcl.server_id == server_id,
                McpToolAcl.tool_id == tool_id,
                McpToolAcl.team_id.in_(team_ids),
            )
        )
        perms = list(result.scalars().all())
        if perms:
            return "use" if "use" in perms else perms[0]

    # 5. Team ACL on server (tool_id IS NULL)
    result = await db.execute(
        select(McpToolAcl.permission).where(
            McpToolAcl.server_id == server_id,
            McpToolAcl.tool_id.is_(None),
            McpToolAcl.team_id.in_(team_ids),
        )
    )
    perms = list(result.scalars().all())
    if perms:
        return "use" if "use" in perms else perms[0]

    # 6. Deny
    return None


async def get_accessible_servers(
    db: AsyncSession, user_external_id: str
) -> list[uuid.UUID]:
    """Return list of server IDs the user has at least 'view' access to."""
    result = await db.execute(select(User).where(User.external_id == user_external_id))
    user = result.scalar_one_or_none()
    if user is None:
        # Even unauthenticated: platform-provided servers are always visible
        result = await db.execute(
            select(McpServer.id).where(McpServer.is_platform_provided.is_(True))
        )
        return list(result.scalars().all())

    if user.is_platform_admin:
        result = await db.execute(select(McpServer.id))
        return list(result.scalars().all())

    # Platform-provided servers are always accessible
    result = await db.execute(
        select(McpServer.id).where(McpServer.is_platform_provided.is_(True))
    )
    server_ids = set(result.scalars().all())

    # Direct user ACL
    result = await db.execute(
        select(McpToolAcl.server_id).where(McpToolAcl.user_id == user.id).distinct()
    )
    server_ids = set(result.scalars().all())

    # Team ACL
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = list(result.scalars().all())
    if team_ids:
        result = await db.execute(
            select(McpToolAcl.server_id)
            .where(McpToolAcl.team_id.in_(team_ids))
            .distinct()
        )
        server_ids.update(result.scalars().all())

    return list(server_ids)

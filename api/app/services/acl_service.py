"""ACL permission resolution.

Resolution order:
1. agent owner → full access
2. direct user ACL entry
3. team ACL entries (user's teams)
4. visibility='public' → implicit 'user' role
5. visibility='team' → implicit 'user' role for team members
6. deny
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, AgentACL, TeamMember, User

# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY = {"viewer": 0, "user": 1, "admin": 2, "owner": 3}

ROLE_PERMISSIONS = {
    "viewer": {"search", "view"},
    "user": {"search", "view", "chat"},
    "admin": {"search", "view", "chat", "view_logs", "edit_config"},
    "owner": {"search", "view", "chat", "view_logs", "edit_config", "manage_acl", "delete"},
}


async def resolve_agent_role(
    db: AsyncSession, user: User, agent: Agent
) -> str | None:
    """Resolve the effective role a user has on an agent. Returns None if no access."""
    # 1. Agent owner → full access
    if agent.owner_id == user.id:
        return "owner"

    # 2. Direct user ACL entry
    result = await db.execute(
        select(AgentACL).where(
            AgentACL.agent_id == agent.id,
            AgentACL.user_id == user.id,
        )
    )
    direct_acl = result.scalar_one_or_none()
    if direct_acl:
        return direct_acl.role

    # 3. Team ACL entries — get user's teams, then check team ACL
    team_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    user_team_ids = [row[0] for row in team_ids_result.all()]

    if user_team_ids:
        team_acl_result = await db.execute(
            select(AgentACL).where(
                AgentACL.agent_id == agent.id,
                AgentACL.team_id.in_(user_team_ids),
            )
        )
        team_acls = team_acl_result.scalars().all()
        if team_acls:
            # Return highest role from team ACLs
            best_role = max(team_acls, key=lambda a: ROLE_HIERARCHY.get(a.role, 0))
            return best_role.role

    # 4. Public agent → implicit 'user' role
    if agent.visibility == "public":
        return "user"

    # 5. Team agent → implicit 'user' for team members
    if agent.visibility == "team" and user_team_ids:
        # Check if any of user's teams match agent owner's teams
        owner_team_ids_result = await db.execute(
            select(TeamMember.team_id).where(TeamMember.user_id == agent.owner_id)
        )
        owner_team_ids = {row[0] for row in owner_team_ids_result.all()}
        if owner_team_ids & set(user_team_ids):
            return "user"

    # 6. Deny
    return None


def has_permission(role: str | None, permission: str) -> bool:
    """Check if a role grants a specific permission."""
    if role is None:
        return False
    return permission in ROLE_PERMISSIONS.get(role, set())


async def check_agent_permission(
    db: AsyncSession, user: User, agent: Agent, permission: str
) -> None:
    """Raise ValueError if user lacks the required permission on the agent."""
    role = await resolve_agent_role(db, user, agent)
    if not has_permission(role, permission):
        raise PermissionError(f"You do not have '{permission}' permission on this agent")

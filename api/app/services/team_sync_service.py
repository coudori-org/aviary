"""Sync OIDC groups (Keycloak/Okta) to Aviary teams on every login.

On each login the token's `groups` claim is the source of truth:
- Teams that appear in the claim are created if they don't exist.
- The user is added as a member to those teams.
- The user is removed from teams they no longer belong to (per the token).

This keeps Aviary team memberships in sync with the identity provider
without requiring a separate admin workflow.
"""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Team, TeamMember

logger = logging.getLogger(__name__)


async def sync_user_teams(
    db: AsyncSession,
    user_id: uuid.UUID,
    group_names: list[str],
) -> None:
    """Reconcile the user's team memberships to match the given OIDC group list."""
    if not group_names:
        # User has no groups — remove all team memberships
        await db.execute(
            delete(TeamMember).where(TeamMember.user_id == user_id)
        )
        return

    # 1. Upsert teams for every group name in the token
    desired_team_ids: set[uuid.UUID] = set()
    for name in group_names:
        result = await db.execute(select(Team).where(Team.name == name))
        team = result.scalar_one_or_none()
        if team is None:
            team = Team(name=name, description=f"Synced from OIDC group '{name}'")
            db.add(team)
            await db.flush()
            logger.info("Created team '%s' (id=%s) from OIDC group", name, team.id)
        desired_team_ids.add(team.id)

    # 2. Fetch current memberships
    result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user_id)
    )
    current_team_ids = {row[0] for row in result.all()}

    # 3. Add missing memberships
    to_add = desired_team_ids - current_team_ids
    for team_id in to_add:
        db.add(TeamMember(team_id=team_id, user_id=user_id, role="member"))

    # 4. Remove stale memberships (user left the group in Keycloak/Okta)
    to_remove = current_team_ids - desired_team_ids
    if to_remove:
        await db.execute(
            delete(TeamMember).where(
                TeamMember.user_id == user_id,
                TeamMember.team_id.in_(to_remove),
            )
        )

    if to_add or to_remove:
        await db.flush()
        logger.info(
            "Synced teams for user %s: added %d, removed %d",
            user_id, len(to_add), len(to_remove),
        )

"""User list and detail pages."""

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Team, TeamMember, User
from app.db import get_db
from app.routers.pages._templates import templates

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def user_list(request: Request, db: AsyncSession = Depends(get_db)):
    from app.routers.users import _sync_keycloak_users
    await _sync_keycloak_users(db)

    result = await db.execute(select(User).order_by(User.created_at.desc()))
    all_users = list(result.scalars().all())

    user_data = []
    for u in all_users:
        result = await db.execute(
            select(Team.name)
            .join(TeamMember, TeamMember.team_id == Team.id)
            .where(TeamMember.user_id == u.id)
        )
        teams = list(result.scalars().all())
        user_data.append({
            "id": str(u.id),
            "external_id": u.external_id,
            "email": u.email,
            "display_name": u.display_name,
            "is_platform_admin": u.is_platform_admin,
            "teams": teams,
            "created_at": u.created_at.isoformat(),
        })

    return templates.TemplateResponse(request, "users.html", {"users": user_data})


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: str, db: AsyncSession = Depends(get_db)):
    from app.routers.users import _vault_list_keys, _vault_get_key

    u_uuid = uuid.UUID(user_id)
    result = await db.execute(select(User).where(User.id == u_uuid))
    user = result.scalar_one_or_none()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    result = await db.execute(
        select(Team.name)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user.id)
    )
    teams = list(result.scalars().all())

    user_data = {
        "id": str(user.id),
        "external_id": user.external_id,
        "email": user.email,
        "display_name": user.display_name,
        "is_platform_admin": user.is_platform_admin,
        "teams": teams,
        "created_at": user.created_at.isoformat(),
    }

    # Fetch Vault credentials
    credentials = []
    try:
        keys = await _vault_list_keys(user.external_id)
        for key in keys:
            key = key.rstrip("/")
            data = await _vault_get_key(user.external_id, key)
            if data:
                token = data.get("value", "")
                masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
                credentials.append({"key": key, "value": masked})
    except Exception:  # Best-effort: Vault may not be reachable
        pass

    return templates.TemplateResponse(request, "user_detail.html", {
        "user": user_data,
        "credentials": credentials,
    })

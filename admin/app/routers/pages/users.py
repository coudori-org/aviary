"""User list and detail pages."""

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import User
from app.db import get_db
from app.routers.pages._templates import templates
from app.routers.users import _sync_keycloak_users, _vault

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/users", response_class=HTMLResponse)
async def user_list(request: Request, db: AsyncSession = Depends(get_db)):
    await _sync_keycloak_users(db)
    all_users = list((await db.execute(
        select(User).order_by(User.created_at.desc())
    )).scalars().all())

    user_data = [
        {
            "id": str(u.id),
            "external_id": u.external_id,
            "email": u.email,
            "display_name": u.display_name,
            "created_at": u.created_at.isoformat(),
        }
        for u in all_users
    ]
    return templates.TemplateResponse(request, "users.html", {"users": user_data})


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(request: Request, user_id: str, db: AsyncSession = Depends(get_db)):
    u_uuid = uuid.UUID(user_id)
    user = (await db.execute(select(User).where(User.id == u_uuid))).scalar_one_or_none()
    if not user:
        return HTMLResponse("<h1>User not found</h1>", status_code=404)

    credentials: list[dict] = []
    try:
        keys = await _vault().list_user_credentials(user.external_id)
        for key in keys:
            token = await _vault().read_user_credential(user.external_id, key)
            if token is None:
                continue
            masked = token[:8] + "..." + token[-4:] if len(token) > 16 else "***"
            credentials.append({"key": key, "value": masked})
    except httpx.HTTPError:
        logger.warning("Vault unreachable while loading user %s credentials", user.id, exc_info=True)

    return templates.TemplateResponse(request, "user_detail.html", {
        "user": {
            "id": str(user.id),
            "external_id": user.external_id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at.isoformat(),
        },
        "credentials": credentials,
    })

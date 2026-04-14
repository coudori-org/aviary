"""Service Accounts admin pages — list + detail/edit."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import Agent, ServiceAccount
from app.db import get_db
from app.routers.pages._templates import templates
from app.routers.service_accounts import DEFAULT_SG, _ensure_default_sg

router = APIRouter()


@router.get("/service-accounts", response_class=HTMLResponse)
async def service_accounts_page(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ServiceAccount).order_by(
            ServiceAccount.is_system.desc(), ServiceAccount.name,
        )
    )
    sas = list(result.scalars().all())
    return templates.TemplateResponse(request, "service_accounts.html", {
        "service_accounts": sas,
        "default_sg": DEFAULT_SG,
    })


@router.post("/service-accounts/create")
async def create_service_account(
    name: str = Form(...),
    description: str = Form(""),
    sg_refs: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    refs = _ensure_default_sg([r for r in sg_refs.split(",")])
    sa = ServiceAccount(
        name=name.strip(),
        description=description or None,
        sg_refs=refs,
        is_system=False,
    )
    db.add(sa)
    try:
        await db.flush()
    except Exception:
        return RedirectResponse("/service-accounts?error=Name+already+exists", status_code=303)
    return RedirectResponse("/service-accounts?flash=Service+account+created", status_code=303)


@router.post("/service-accounts/{sa_id}/update")
async def update_service_account(
    sa_id: uuid.UUID,
    description: str = Form(""),
    sg_refs: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        return RedirectResponse("/service-accounts?error=Not+found", status_code=303)
    sa.description = description or None
    sa.sg_refs = _ensure_default_sg([r for r in sg_refs.split(",")])
    await db.flush()
    return RedirectResponse("/service-accounts?flash=Saved", status_code=303)


@router.post("/service-accounts/{sa_id}/delete")
async def delete_service_account(sa_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        return RedirectResponse("/service-accounts?error=Not+found", status_code=303)
    if sa.is_system:
        return RedirectResponse("/service-accounts?error=System+SA+cannot+be+deleted", status_code=303)

    bound = await db.execute(select(Agent.id).where(Agent.service_account_id == sa_id).limit(1))
    if bound.scalar_one_or_none():
        return RedirectResponse(
            "/service-accounts?error=Still+bound+to+one+or+more+agents", status_code=303,
        )
    await db.delete(sa)
    await db.flush()
    return RedirectResponse("/service-accounts?flash=Deleted", status_code=303)

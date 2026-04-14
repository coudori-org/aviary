"""Service Account JSON API — CRUD for egress identity + SG binding."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aviary_shared.db.models import ServiceAccount
from app.db import get_db

router = APIRouter()


class SAResponse(BaseModel):
    id: str
    name: str
    description: str | None
    sg_refs: list[str]
    is_system: bool

    @classmethod
    def from_entity(cls, sa: ServiceAccount) -> "SAResponse":
        return cls(
            id=str(sa.id),
            name=sa.name,
            description=sa.description,
            sg_refs=list(sa.sg_refs or []),
            is_system=sa.is_system,
        )


class SACreateRequest(BaseModel):
    name: str
    description: str | None = None
    sg_refs: list[str] = []


class SAUpdateRequest(BaseModel):
    description: str | None = None
    sg_refs: list[str] | None = None


DEFAULT_SG = "default-sg"


def _ensure_default_sg(sg_refs: list[str]) -> list[str]:
    """`default-sg` is always bound — matches AWS account-default-SG semantics."""
    seen: set[str] = set()
    ordered: list[str] = [DEFAULT_SG]
    seen.add(DEFAULT_SG)
    for ref in sg_refs:
        ref = ref.strip()
        if ref and ref not in seen:
            ordered.append(ref)
            seen.add(ref)
    return ordered


@router.get("")
async def list_service_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ServiceAccount).order_by(ServiceAccount.is_system.desc(), ServiceAccount.name)
    )
    return {"items": [SAResponse.from_entity(sa).model_dump() for sa in result.scalars().all()]}


@router.post("", status_code=201)
async def create_service_account(body: SACreateRequest, db: AsyncSession = Depends(get_db)):
    sa = ServiceAccount(
        name=body.name.strip(),
        description=body.description,
        sg_refs=_ensure_default_sg(body.sg_refs),
        is_system=False,
    )
    db.add(sa)
    try:
        await db.flush()
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"ServiceAccount '{body.name}' already exists") from e
    return SAResponse.from_entity(sa).model_dump()


@router.get("/{sa_id}")
async def get_service_account(sa_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=404, detail="ServiceAccount not found")
    return SAResponse.from_entity(sa).model_dump()


@router.put("/{sa_id}")
async def update_service_account(
    sa_id: uuid.UUID, body: SAUpdateRequest, db: AsyncSession = Depends(get_db),
):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=404, detail="ServiceAccount not found")
    if body.description is not None:
        sa.description = body.description
    if body.sg_refs is not None:
        sa.sg_refs = _ensure_default_sg(body.sg_refs)
    await db.flush()
    return SAResponse.from_entity(sa).model_dump()


@router.delete("/{sa_id}", status_code=204)
async def delete_service_account(sa_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=404, detail="ServiceAccount not found")
    if sa.is_system:
        raise HTTPException(status_code=400, detail="System ServiceAccounts cannot be deleted")
    # FK is ON DELETE RESTRICT — DB will reject if any agent still references it.
    try:
        await db.delete(sa)
        await db.flush()
    except Exception as e:
        raise HTTPException(
            status_code=409,
            detail="ServiceAccount is still bound to one or more agents",
        ) from e
    return None

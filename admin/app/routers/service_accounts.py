"""Service Account JSON API — CRUD for extra SG bundles.

Each ServiceAccount names a bundle of SG refs an agent can opt into on top
of the namespace baseline egress policy. Agents with `service_account_id=NULL`
get only the baseline; bound agents get baseline + the SA's sg_refs.
"""

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

    @classmethod
    def from_entity(cls, sa: ServiceAccount) -> "SAResponse":
        return cls(
            id=str(sa.id),
            name=sa.name,
            description=sa.description,
            sg_refs=list(sa.sg_refs or []),
        )


class SACreateRequest(BaseModel):
    name: str
    description: str | None = None
    sg_refs: list[str] = []


class SAUpdateRequest(BaseModel):
    description: str | None = None
    sg_refs: list[str] | None = None


def _normalize_refs(sg_refs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in sg_refs:
        ref = ref.strip()
        if ref and ref not in seen:
            out.append(ref)
            seen.add(ref)
    return out


@router.get("")
async def list_service_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceAccount).order_by(ServiceAccount.name))
    return {"items": [SAResponse.from_entity(sa).model_dump() for sa in result.scalars().all()]}


@router.post("", status_code=201)
async def create_service_account(body: SACreateRequest, db: AsyncSession = Depends(get_db)):
    sa = ServiceAccount(
        name=body.name.strip(),
        description=body.description,
        sg_refs=_normalize_refs(body.sg_refs),
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
        sa.sg_refs = _normalize_refs(body.sg_refs)
    await db.flush()
    return SAResponse.from_entity(sa).model_dump()


@router.delete("/{sa_id}", status_code=204)
async def delete_service_account(sa_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    sa = await db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=404, detail="ServiceAccount not found")
    # FK is ON DELETE SET NULL — bound agents fall back to baseline egress.
    await db.delete(sa)
    await db.flush()
    return None

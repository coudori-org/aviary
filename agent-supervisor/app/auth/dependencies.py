"""Identity resolution for supervisor endpoints.

Three auth paths, in priority order:
  1. Worker — `X-Aviary-Worker-Key` + body `on_behalf_of_sub`. Works
     regardless of IdP configuration.
  2. Dev    — fires unconditionally when `OIDC_ISSUER` is unset (after
     the worker check). Caller is treated as `dev_user_sub`. The dev
     path is **gated solely by the env**, not by request shape — any
     production deployment must set `OIDC_ISSUER`.
  3. User   — when IdP is enabled, every non-worker request must carry a
     valid `Authorization: Bearer <JWT>`. Missing / malformed / invalid
     tokens are 401.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.auth.oidc import TokenClaims, dev_user_sub, idp_enabled, validate_token
from app.config import settings

_BEARER_PREFIX = "bearer "


@dataclass
class IdentityContext:
    sub: str
    user_token: str | None
    via: str  # "user" | "worker" | "dev"


def _dev_identity() -> IdentityContext:
    return IdentityContext(sub=dev_user_sub(), user_token=None, via="dev")


def _extract_bearer(auth_header: str) -> str:
    if not auth_header.lower().startswith(_BEARER_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = auth_header[len(_BEARER_PREFIX):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty Bearer token")
    return token


async def resolve_identity(request: Request, body: dict) -> IdentityContext:
    worker_key = request.headers.get("x-aviary-worker-key")
    if worker_key is not None:
        expected = settings.worker_shared_secret
        if not expected or not hmac.compare_digest(worker_key, expected):
            raise HTTPException(status_code=401, detail="Invalid worker key")
        sub = body.get("on_behalf_of_sub")
        if not sub:
            raise HTTPException(
                status_code=400, detail="on_behalf_of_sub required for worker auth"
            )
        return IdentityContext(sub=sub, user_token=None, via="worker")

    if not idp_enabled():
        return _dev_identity()

    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = _extract_bearer(auth_header)
    try:
        claims = await validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return IdentityContext(sub=claims.sub, user_token=token, via="user")


async def get_current_user(request: Request) -> TokenClaims:
    if not idp_enabled():
        return await validate_token("")
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = _extract_bearer(auth_header)
    try:
        return await validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def extract_bearer_token(request: Request) -> str:
    return _extract_bearer(request.headers.get("authorization", ""))

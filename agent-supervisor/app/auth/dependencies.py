"""Identity resolution for supervisor endpoints.

Two authentication paths:
  1. User path — `Authorization: Bearer <JWT>`. Validated against Keycloak;
     the JWT is forwarded to the runtime so LiteLLM can inject the user's
     per-backend API key.
  2. Worker path — `X-Aviary-Worker-Key: <shared secret>` + body field
     `on_behalf_of_sub`. Used by the Temporal workflow worker for runs that
     outlive any interactive browser session (deployed cron / webhook
     triggers, long-running workflows).
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.auth.oidc import TokenClaims, validate_token
from app.config import settings


@dataclass
class IdentityContext:
    sub: str
    user_token: str | None  # None on worker path — no JWT to forward
    via: str                # "user" | "worker"


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

    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    token = auth_header.split(None, 1)[1].strip()
    try:
        claims = await validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return IdentityContext(sub=claims.sub, user_token=token, via="user")


# ── Legacy helpers retained for non-message endpoints that still use a plain
# JWT dependency (e.g. anything without a request body) ─────────────────────

async def get_current_user(request: Request) -> TokenClaims:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(None, 1)[1].strip()
    try:
        return await validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth_header.split(None, 1)[1].strip()

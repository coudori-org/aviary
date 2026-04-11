"""Server-side session storage backing the cookie-based auth flow.

The browser holds only an opaque session id in an httpOnly cookie; the
OIDC tokens live here in Redis. `get_fresh_session` transparently
refreshes the access token via the OIDC server when it nears expiry,
which is what keeps long-lived WebSockets working past the 5-minute
Keycloak access-token TTL.
"""

import json
import logging
import secrets
import time
from dataclasses import dataclass

import httpx

from app.auth.oidc import refresh_tokens, validate_token
from app.services.redis_service import get_client

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "aviary_session"
SESSION_ID_BYTES = 32
REDIS_KEY_PREFIX = "auth:session:"

# Sliding TTL — bumped on every successful access. Bounded above by
# Keycloak's refresh token absolute lifetime, which the OIDC server
# enforces independently.
SESSION_TTL_SECONDS = 24 * 60 * 60

REFRESH_BUFFER_SECONDS = 60


@dataclass
class SessionData:
    user_external_id: str
    access_token: str
    refresh_token: str
    id_token: str | None
    access_token_expires_at: int

    def to_json(self) -> str:
        return json.dumps({
            "user_external_id": self.user_external_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "access_token_expires_at": self.access_token_expires_at,
        })

    @classmethod
    def from_json(cls, raw: str) -> "SessionData":
        d = json.loads(raw)
        return cls(
            user_external_id=d["user_external_id"],
            access_token=d["access_token"],
            refresh_token=d["refresh_token"],
            id_token=d.get("id_token"),
            access_token_expires_at=int(d["access_token_expires_at"]),
        )


def _redis_key(session_id: str) -> str:
    return f"{REDIS_KEY_PREFIX}{session_id}"


def _new_session_id() -> str:
    return secrets.token_urlsafe(SESSION_ID_BYTES)


async def create_session(
    *,
    user_external_id: str,
    access_token: str,
    refresh_token: str,
    id_token: str | None,
    expires_in: int,
) -> str:
    client = get_client()
    if not client:
        raise RuntimeError("Redis is unavailable; cannot create auth session")

    session_id = _new_session_id()
    data = SessionData(
        user_external_id=user_external_id,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
        access_token_expires_at=int(time.time()) + int(expires_in),
    )
    await client.set(_redis_key(session_id), data.to_json(), ex=SESSION_TTL_SECONDS)
    return session_id


async def _load(session_id: str) -> SessionData | None:
    client = get_client()
    if not client:
        return None
    raw = await client.get(_redis_key(session_id))
    if not raw:
        return None
    try:
        return SessionData.from_json(raw)
    except (ValueError, KeyError):
        logger.warning("Dropping corrupted session entry %s", session_id)
        await client.delete(_redis_key(session_id))
        return None


async def _save(session_id: str, data: SessionData) -> None:
    client = get_client()
    if not client:
        return
    await client.set(_redis_key(session_id), data.to_json(), ex=SESSION_TTL_SECONDS)


async def get_fresh_session(session_id: str) -> SessionData | None:
    """Return session data with a guaranteed-fresh access token, or None
    if the session is gone or refresh failed."""
    data = await _load(session_id)
    if data is None:
        return None
    if data.access_token_expires_at - int(time.time()) > REFRESH_BUFFER_SECONDS:
        return data

    try:
        new_tokens = await refresh_tokens(data.refresh_token)
    except httpx.HTTPStatusError as e:
        # 4xx = Keycloak definitively rejected this refresh token. 5xx /
        # network = transient blip; leave the session alone so the next
        # attempt can retry.
        status = e.response.status_code if e.response is not None else 0
        if 400 <= status < 500:
            logger.info("Refresh token rejected (%s) for session %s — clearing", status, session_id)
            await delete_session(session_id)
            return None
        logger.warning("Transient refresh failure (%s) for session %s — keeping session", status, session_id)
        return None
    except httpx.HTTPError as e:
        logger.warning("Transient refresh failure (%s) for session %s — keeping session", e.__class__.__name__, session_id)
        return None

    new_access = new_tokens["access_token"]
    try:
        claims = await validate_token(new_access)
    except ValueError:
        logger.warning("Refreshed access token failed validation for session %s", session_id)
        await delete_session(session_id)
        return None
    # Defense against token swap during refresh.
    if claims.sub != data.user_external_id:
        logger.error(
            "Refreshed token subject mismatch (was=%s now=%s) — dropping session",
            data.user_external_id, claims.sub,
        )
        await delete_session(session_id)
        return None

    data.access_token = new_access
    data.refresh_token = new_tokens.get("refresh_token") or data.refresh_token
    data.id_token = new_tokens.get("id_token") or data.id_token
    data.access_token_expires_at = int(time.time()) + int(new_tokens.get("expires_in", 300))
    await _save(session_id, data)
    return data


async def delete_session(session_id: str) -> None:
    client = get_client()
    if not client:
        return
    await client.delete(_redis_key(session_id))

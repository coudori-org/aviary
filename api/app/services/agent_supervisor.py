"""Agent Supervisor client — session-centric, stateless. All routing info
(runtime_endpoint) comes from the agent row on the API side and rides in
the request body."""

import logging

import httpx

from aviary_shared.http import ServiceClient

from app.config import settings

logger = logging.getLogger(__name__)

_supervisor = ServiceClient(base_url=settings.agent_supervisor_url)


async def init_client() -> None:
    await _supervisor.init()


async def close_client() -> None:
    await _supervisor.close()


async def publish_stream(session_id: str, body: dict, user_token: str) -> dict:
    """Ask the supervisor to consume runtime SSE, publish to Redis, assemble
    the final response, and return it.

    The supervisor authenticates `user_token` (OIDC Bearer), extracts the
    user's `sub`, and pulls per-user credentials (GitHub token, etc.) from
    Vault — the API no longer touches Vault for runtime credentials.

    Returns `{status, reached_runtime, assembled_text?, assembled_blocks?, message?}`.
    """
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/publish",
        json=body,
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=None,
    )
    resp.raise_for_status()
    return resp.json()


async def abort_session(
    session_id: str,
    agent_id: str | None = None,
) -> None:
    """Best-effort abort. Racy with normal completion."""
    try:
        resp = await _supervisor.client.post(
            f"/v1/sessions/{session_id}/abort",
            json={"agent_id": agent_id},
            timeout=5,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Failed to abort session %s", session_id, exc_info=True)


async def cleanup_session(
    session_id: str,
    agent_id: str,
    runtime_endpoint: str | None = None,
) -> None:
    """Best-effort workspace cleanup."""
    try:
        resp = await _supervisor.client.request(
            "DELETE",
            f"/v1/sessions/{session_id}",
            json={"agent_id": agent_id, "runtime_endpoint": runtime_endpoint},
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Session cleanup failed for %s", session_id, exc_info=True)


def get_stream_url(session_id: str) -> str:
    """Direct SSE passthrough endpoint — for workflow / A2A sub-agent callers
    that do in-process event transformation rather than Redis assembly."""
    return f"{settings.agent_supervisor_url}/v1/sessions/{session_id}/message"


async def health_check() -> bool:
    try:
        resp = await _supervisor.client.get("/v1/health")
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.debug("Supervisor health check failed", exc_info=True)
        return False

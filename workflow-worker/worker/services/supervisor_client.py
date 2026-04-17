"""HTTP client for the agent supervisor.

Two auth paths mirror supervisor's own resolver:
  * `user_token` present  → `Authorization: Bearer <jwt>` (same path that
    interactive chat uses — LiteLLM's per-user key hook works unchanged).
  * `user_token` is None  → `X-Aviary-Worker-Key + on_behalf_of_sub`
    fallback for cron / webhook triggers that don't have a live user JWT.
"""

from __future__ import annotations

import httpx

from worker.config import settings


def _headers_for(user_token: str | None) -> dict[str, str]:
    if user_token:
        return {"Authorization": f"Bearer {user_token}"}
    return {"X-Aviary-Worker-Key": settings.worker_shared_secret}


async def post_message(
    session_id: str, body: dict, user_token: str | None = None,
) -> dict:
    async with httpx.AsyncClient(timeout=None) as cli:
        resp = await cli.post(
            f"{settings.supervisor_url}/v1/sessions/{session_id}/message",
            json=body, headers=_headers_for(user_token),
        )
        resp.raise_for_status()
        return resp.json()


async def abort_stream(stream_id: str, user_token: str | None = None) -> None:
    async with httpx.AsyncClient(timeout=5.0) as cli:
        try:
            await cli.post(
                f"{settings.supervisor_url}/v1/streams/{stream_id}/abort",
                headers=_headers_for(user_token),
            )
        except httpx.HTTPError:
            pass

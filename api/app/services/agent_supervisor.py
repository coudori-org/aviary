"""Supervisor HTTP client.

The supervisor is the session-stream gateway: API POSTs a message, the
supervisor drives the runtime SSE → Redis → assembled response, and the
API persists the assembled message. Auth to the supervisor is always an
OIDC Bearer (user JWT) — the supervisor validates and uses the sub claim
to inject per-user credentials from Vault before it reaches the runtime.
"""

import logging

import httpx

from aviary_shared.http import ServiceClient

from app.config import settings

logger = logging.getLogger(__name__)

_supervisor = ServiceClient(base_url=settings.agent_supervisor_url)


def _auth_headers(user_token: str) -> dict[str, str]:
    # No-IdP dev mode has no JWT — omit the header so the supervisor falls
    # through to its dev path.
    return {"Authorization": f"Bearer {user_token}"} if user_token else {}


async def init_client() -> None:
    await _supervisor.init()


async def close_client() -> None:
    await _supervisor.close()


async def post_message(
    session_id: str, body: dict, user_token: str,
    timeout: float | None = None,
) -> dict:
    """Drive a single agent turn. Blocks until the stream is assembled.

    Returns `{status, stream_id, reached_runtime, assembled_text?, assembled_blocks?, structured_output?, message?}`.

    `timeout` caps the whole round-trip from the API's perspective — leave
    as None for chat (the supervisor owns end-to-end lifecycle), set an
    explicit seconds value for one-shot helper calls so we don't hang when
    the runtime silently stalls.
    """
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/message",
        json=body,
        headers=_auth_headers(user_token),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


async def abort_stream(stream_id: str) -> None:
    try:
        resp = await _supervisor.client.post(
            f"/v1/streams/{stream_id}/abort", timeout=5,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Failed to abort stream %s", stream_id, exc_info=True)


async def cleanup_session(
    session_id: str,
    agent_id: str,
    runtime_endpoint: str | None = None,
) -> None:
    """Best-effort workspace cleanup on the runtime."""
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


async def fetch_workspace_tree(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
    include_hidden: bool,
) -> tuple[int, dict]:
    """Returns the supervisor's raw (status, payload) so the API can propagate 4xx as-is."""
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/tree",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "path": rel_path,
            "include_hidden": include_hidden,
        },
        headers=_auth_headers(user_token),
        timeout=15,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def fetch_workspace_file(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
) -> tuple[int, dict]:
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/file",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "path": rel_path,
        },
        headers=_auth_headers(user_token),
        timeout=30,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def stat_workspace_file(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
) -> tuple[int, dict]:
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/stat",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "path": rel_path,
        },
        headers=_auth_headers(user_token),
        timeout=15,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def write_workspace_file(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
    content: str,
    encoding: str,
    expected_mtime: int | None,
    overwrite: bool,
) -> tuple[int, dict]:
    body: dict = {
        "runtime_endpoint": runtime_endpoint,
        "agent_id": agent_id,
        "path": rel_path,
        "content": content,
        "encoding": encoding,
        "overwrite": overwrite,
    }
    if expected_mtime is not None:
        body["expected_mtime"] = expected_mtime
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/write",
        json=body,
        headers=_auth_headers(user_token),
        timeout=60,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def create_workspace_dir(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
) -> tuple[int, dict]:
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/mkdir",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "path": rel_path,
        },
        headers=_auth_headers(user_token),
        timeout=15,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def delete_workspace_entry(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
    recursive: bool,
) -> tuple[int, dict]:
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/delete",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "path": rel_path,
            "recursive": recursive,
        },
        headers=_auth_headers(user_token),
        timeout=30,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def move_workspace_entry(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    from_path: str,
    to_path: str,
) -> tuple[int, dict]:
    resp = await _supervisor.client.post(
        f"/v1/sessions/{session_id}/workspace/move",
        json={
            "runtime_endpoint": runtime_endpoint,
            "agent_id": agent_id,
            "from": from_path,
            "to": to_path,
        },
        headers=_auth_headers(user_token),
        timeout=15,
    )
    try:
        payload = resp.json()
    except ValueError:
        payload = {"error": "invalid supervisor response"}
    return resp.status_code, payload


async def stream_workspace_download(
    session_id: str,
    user_token: str,
    runtime_endpoint: str | None,
    agent_id: str | None,
    rel_path: str,
    inline: bool = False,
):
    """Open a streaming response on the supervisor's download endpoint.

    Returns (response, close_callable). Caller must await close() after
    consuming the stream (or on error).
    """
    body = {
        "runtime_endpoint": runtime_endpoint,
        "agent_id": agent_id,
        "path": rel_path,
        "inline": inline,
    }
    req = _supervisor.client.build_request(
        "POST",
        f"/v1/sessions/{session_id}/workspace/download",
        json=body,
        headers=_auth_headers(user_token),
    )
    resp = await _supervisor.client.send(req, stream=True)
    return resp


async def cleanup_workflow_artifacts(
    root_run_id: str,
    runtime_endpoint: str | None = None,
) -> None:
    """Best-effort wipe of a workflow run's artifact tree on the PVC."""
    try:
        resp = await _supervisor.client.request(
            "DELETE",
            f"/v1/workflows/{root_run_id}/artifacts",
            json={"runtime_endpoint": runtime_endpoint},
            timeout=15,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            "Artifact cleanup failed for root_run=%s", root_run_id, exc_info=True,
        )


async def health_check() -> bool:
    try:
        resp = await _supervisor.client.get("/v1/health")
        return resp.status_code == 200
    except httpx.HTTPError:
        logger.debug("Supervisor health check failed", exc_info=True)
        return False

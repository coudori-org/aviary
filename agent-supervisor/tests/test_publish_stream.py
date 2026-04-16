"""/v1/sessions/{sid}/publish — consumes runtime SSE, publishes to Redis, returns assembled message."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.oidc import TokenClaims


_CLAIMS = TokenClaims(sub="user-abc", email="u@test", display_name="u")
_AUTH = {"Authorization": "Bearer dummy-jwt"}


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class _FakeSSEResponse:
    def __init__(self, lines: list[str], status_code: int = 200):
        self._lines = lines
        self.status_code = status_code

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return "\n".join(self._lines).encode()


class _FakeStreamCtx:
    def __init__(self, resp, captured: dict | None = None):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, resp, captured: dict | None = None):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kwargs):
        if self._captured is not None:
            self._captured["url"] = url
            self._captured["json"] = kwargs.get("json")
        return _FakeStreamCtx(self._resp)


def _patch_runtime_stream(lines: list[str], status: int = 200, captured: dict | None = None):
    resp = _FakeSSEResponse(lines, status)
    return patch("httpx.AsyncClient", return_value=_FakeClient(resp, captured))


def _patch_auth_and_vault(credentials: dict[str, str] | None = None):
    """Bypass real OIDC validation and Vault lookups."""
    return (
        patch("app.auth.dependencies.validate_token", AsyncMock(return_value=_CLAIMS)),
        patch(
            "app.routers.agents.fetch_user_credentials",
            AsyncMock(return_value=credentials or {}),
        ),
    )


@pytest.mark.asyncio
async def test_publish_rejects_missing_bearer(client):
    resp = client.post(
        "/v1/sessions/s1/publish",
        json={"agent_config": {"agent_id": "a1"}},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_publish_streams_events_to_redis(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "chunk", "content": "hello"}',
        'data: {"type": "chunk", "content": " world"}',
    ]
    auth_p, vault_p = _patch_auth_and_vault({"github_token": "ghp_xyz"})
    captured: dict = {}
    with _patch_runtime_stream(lines, captured=captured), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock) as append, \
         patch("app.routers.agents.redis_client.publish_message", new_callable=AsyncMock) as publish, \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status, \
         patch("app.routers.agents.redis_client.get_stream_chunks", new_callable=AsyncMock, return_value=[
             {"type": "chunk", "content": "hello"},
             {"type": "chunk", "content": " world"},
         ]):
        resp = client.post(
            "/v1/sessions/s1/publish",
            headers=_AUTH,
            json={
                "runtime_endpoint": None,
                "content_parts": [{"text": "hi"}],
                "agent_config": {"agent_id": "a1"},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["reached_runtime"] is True
    assert data["assembled_text"] == "hello world"

    # Validated identity + Vault creds were injected into the runtime body.
    forwarded = captured["json"]["agent_config"]
    assert forwarded["user_token"] == "dummy-jwt"
    assert forwarded["user_external_id"] == "user-abc"
    assert forwarded["credentials"] == {"github_token": "ghp_xyz"}

    # query_started is control-only, not published
    assert append.await_count == 2
    assert publish.await_count == 2
    set_status.assert_awaited_with("s1", "complete")


@pytest.mark.asyncio
async def test_publish_omits_credentials_when_vault_empty(client):
    lines = ['data: {"type": "query_started"}']
    auth_p, vault_p = _patch_auth_and_vault({})
    captured: dict = {}
    with _patch_runtime_stream(lines, captured=captured), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_message", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.get_stream_chunks", new_callable=AsyncMock, return_value=[]):
        client.post(
            "/v1/sessions/s1/publish",
            headers=_AUTH,
            json={
                "agent_config": {"agent_id": "a1", "credentials": {"github_token": "stale"}},
            },
        )

    forwarded = captured["json"]["agent_config"]
    # A stale caller-supplied credentials dict must be stripped when Vault is empty.
    assert "credentials" not in forwarded
    assert forwarded["user_external_id"] == "user-abc"


@pytest.mark.asyncio
async def test_publish_reports_runtime_error_event(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "error", "message": "boom"}',
    ]
    auth_p, vault_p = _patch_auth_and_vault()
    with _patch_runtime_stream(lines), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_message", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status:
        resp = client.post(
            "/v1/sessions/s1/publish",
            headers=_AUTH,
            json={"agent_config": {"agent_id": "a1"}},
        )

    data = resp.json()
    assert data["status"] == "error"
    assert data["message"] == "boom"
    assert data["reached_runtime"] is True
    set_status.assert_awaited_with("s1", "error")


@pytest.mark.asyncio
async def test_publish_reports_http_error_before_runtime(client):
    resp_obj = _FakeSSEResponse(["error body"], status_code=500)
    auth_p, vault_p = _patch_auth_and_vault()
    with patch("httpx.AsyncClient", return_value=_FakeClient(resp_obj)), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status:
        resp = client.post(
            "/v1/sessions/s1/publish",
            headers=_AUTH,
            json={"agent_config": {"agent_id": "a1"}},
        )

    data = resp.json()
    assert data["status"] == "error"
    assert data["reached_runtime"] is False
    set_status.assert_awaited_with("s1", "error")


@pytest.mark.asyncio
async def test_abort_unknown_session_broadcasts_to_other_replicas(client):
    """When the session isn't on this replica, publish to the supervisor
    fan-out channel so whichever replica holds it can cancel."""
    with patch(
        "app.routers.agents.redis_client.publish_abort", new_callable=AsyncMock
    ) as pub:
        resp = client.post("/v1/sessions/unknown/abort", json={"agent_id": "a1"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["via"] == "broadcast"
    pub.assert_awaited_once_with("unknown", "a1")


@pytest.mark.asyncio
async def test_cancel_local_cancels_matching_task():
    """Simulate a broadcast arriving at this replica — the listener should
    cancel the matching in-memory publish task via _cancel_local."""
    import contextlib
    from app.routers import agents as router_mod

    async def runner():
        await asyncio.sleep(3600)

    task = asyncio.create_task(runner())
    key = router_mod._registry_key("s1", "a1")
    router_mod._active[key] = task
    try:
        assert router_mod._cancel_local("s1", "a1") is True
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()
    finally:
        router_mod._active.pop(key, None)


@pytest.mark.asyncio
async def test_cancel_local_returns_false_when_missing():
    from app.routers import agents as router_mod
    assert router_mod._cancel_local("missing", "a1") is False

"""/v1/sessions/{sid}/message — consume runtime SSE, publish to Redis, return assembled."""

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
    def __init__(self, resp):
        self._resp = resp

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
    return (
        patch("app.auth.dependencies.validate_token", AsyncMock(return_value=_CLAIMS)),
        patch(
            "app.routers.agents.fetch_user_credentials",
            AsyncMock(return_value=credentials or {}),
        ),
    )


_MIN_AGENT_CONFIG = {
    "agent_id": "a1",
    "runtime_endpoint": None,
    "model_config": {"backend": "anthropic", "model": "claude-sonnet"},
    "instruction": "",
    "tools": [],
    "mcp_servers": {},
}


def _body():
    return {
        "session_id": "s1",
        "content_parts": [{"text": "hi"}],
        "agent_config": dict(_MIN_AGENT_CONFIG),
    }


@pytest.mark.asyncio
async def test_message_rejects_missing_bearer(client):
    resp = client.post("/v1/sessions/s1/message", json=_body())
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_message_streams_events_and_injects_credentials(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "chunk", "content": "hello"}',
        'data: {"type": "chunk", "content": " world"}',
    ]
    auth_p, vault_p = _patch_auth_and_vault({"github_token": "ghp_xyz"})
    captured: dict = {}
    with _patch_runtime_stream(lines, captured=captured), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock) as append, \
         patch("app.routers.agents.redis_client.publish_event", new_callable=AsyncMock) as publish, \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_latest_stream", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.get_stream_chunks", new_callable=AsyncMock, return_value=[
             {"type": "chunk", "content": "hello"},
             {"type": "chunk", "content": " world"},
         ]):
        resp = client.post("/v1/sessions/s1/message", headers=_AUTH, json=_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["reached_runtime"] is True
    assert data["assembled_text"] == "hello world"
    assert data["stream_id"]

    forwarded = captured["json"]["agent_config"]
    assert forwarded["user_token"] == "dummy-jwt"
    assert forwarded["user_external_id"] == "user-abc"
    assert forwarded["credentials"] == {"github_token": "ghp_xyz"}

    # chunks appended once each; publish also fires stream_started + stream_complete + chunks
    assert append.await_count == 2
    assert publish.await_count >= 2


@pytest.mark.asyncio
async def test_message_omits_credentials_when_vault_empty(client):
    lines = ['data: {"type": "query_started"}']
    auth_p, vault_p = _patch_auth_and_vault({})
    captured: dict = {}
    body = _body()
    body["agent_config"]["credentials"] = {"github_token": "stale"}
    with _patch_runtime_stream(lines, captured=captured), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_event", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_latest_stream", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.get_stream_chunks", new_callable=AsyncMock, return_value=[]):
        client.post("/v1/sessions/s1/message", headers=_AUTH, json=body)

    forwarded = captured["json"]["agent_config"]
    assert "credentials" not in forwarded
    assert forwarded["user_external_id"] == "user-abc"


@pytest.mark.asyncio
async def test_message_reports_runtime_error_event(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "error", "message": "boom"}',
    ]
    auth_p, vault_p = _patch_auth_and_vault()
    with _patch_runtime_stream(lines), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_event", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status, \
         patch("app.routers.agents.redis_client.set_session_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_latest_stream", new_callable=AsyncMock):
        resp = client.post("/v1/sessions/s1/message", headers=_AUTH, json=_body())

    data = resp.json()
    assert data["status"] == "error"
    assert data["message"] == "boom"
    assert data["reached_runtime"] is True
    set_status.assert_any_await(data["stream_id"], "error")


@pytest.mark.asyncio
async def test_message_reports_http_error_before_runtime(client):
    resp_obj = _FakeSSEResponse(["error body"], status_code=500)
    auth_p, vault_p = _patch_auth_and_vault()
    with patch("httpx.AsyncClient", return_value=_FakeClient(resp_obj)), auth_p, vault_p, \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_event", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_status", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_session_latest_stream", new_callable=AsyncMock):
        resp = client.post("/v1/sessions/s1/message", headers=_AUTH, json=_body())

    data = resp.json()
    assert data["status"] == "error"
    assert data["reached_runtime"] is False


@pytest.mark.asyncio
async def test_abort_unknown_stream_broadcasts(client):
    with patch(
        "app.routers.agents.redis_client.publish_abort", new_callable=AsyncMock
    ) as pub:
        resp = client.post("/v1/streams/unknown/abort")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["via"] == "broadcast"
    pub.assert_awaited_once_with("unknown")


@pytest.mark.asyncio
async def test_cancel_local_cancels_matching_task():
    import contextlib
    from app.routers import agents as router_mod

    async def runner():
        await asyncio.sleep(3600)

    task = asyncio.create_task(runner())
    router_mod._active["sid-1"] = task
    try:
        assert router_mod._cancel_local("sid-1") is True
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.cancelled()
    finally:
        router_mod._active.pop("sid-1", None)


@pytest.mark.asyncio
async def test_cancel_local_returns_false_when_missing():
    from app.routers import agents as router_mod
    assert router_mod._cancel_local("missing") is False

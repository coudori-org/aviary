"""/v1/sessions/{sid}/publish — consumes runtime SSE, publishes to Redis, returns assembled message."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


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
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, **kwargs):
        return _FakeStreamCtx(self._resp)


def _patch_runtime_stream(lines: list[str], status: int = 200):
    resp = _FakeSSEResponse(lines, status)
    return patch("httpx.AsyncClient", return_value=_FakeClient(resp))


@pytest.mark.asyncio
async def test_publish_streams_events_to_redis(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "chunk", "content": "hello"}',
        'data: {"type": "chunk", "content": " world"}',
    ]
    with _patch_runtime_stream(lines), \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock) as append, \
         patch("app.routers.agents.redis_client.publish_message", new_callable=AsyncMock) as publish, \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status, \
         patch("app.routers.agents.redis_client.get_stream_chunks", new_callable=AsyncMock, return_value=[
             {"type": "chunk", "content": "hello"},
             {"type": "chunk", "content": " world"},
         ]):
        resp = client.post(
            "/v1/sessions/s1/publish",
            json={"runtime_endpoint": None, "content_parts": [{"text": "hi"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["reached_runtime"] is True
    assert data["assembled_text"] == "hello world"

    # query_started is control-only, not published
    assert append.await_count == 2
    assert publish.await_count == 2
    set_status.assert_awaited_with("s1", "complete")


@pytest.mark.asyncio
async def test_publish_reports_runtime_error_event(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "error", "message": "boom"}',
    ]
    with _patch_runtime_stream(lines), \
         patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.publish_message", new_callable=AsyncMock), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status:
        resp = client.post("/v1/sessions/s1/publish", json={})

    data = resp.json()
    assert data["status"] == "error"
    assert data["message"] == "boom"
    assert data["reached_runtime"] is True
    set_status.assert_awaited_with("s1", "error")


@pytest.mark.asyncio
async def test_publish_reports_http_error_before_runtime(client):
    resp_obj = _FakeSSEResponse(["error body"], status_code=500)
    with patch("httpx.AsyncClient", return_value=_FakeClient(resp_obj)), \
         patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock) as set_status:
        resp = client.post("/v1/sessions/s1/publish", json={})

    data = resp.json()
    assert data["status"] == "error"
    assert data["reached_runtime"] is False
    set_status.assert_awaited_with("s1", "error")

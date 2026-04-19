"""POST /v1/sessions/{sid}/workspace/{tree,file} — proxy to runtime."""

from __future__ import annotations

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


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp, captured: dict | None = None):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, timeout=None):
        if self._captured is not None:
            self._captured["url"] = url
            self._captured["params"] = params
        return self._resp


def _patch_runtime(payload, status=200, captured=None):
    return patch("httpx.AsyncClient", return_value=_FakeClient(_FakeResponse(status, payload), captured))


def _patch_auth():
    return patch("app.auth.dependencies.validate_token", AsyncMock(return_value=_CLAIMS))


def test_tree_requires_bearer(client):
    resp = client.post("/v1/sessions/s-1/workspace/tree", json={"path": "/"})
    assert resp.status_code == 401


def test_tree_proxies_payload_and_forwards_params(client):
    captured: dict = {}
    payload = {"path": "/", "entries": [{"name": "README.md", "type": "file"}]}
    with _patch_auth(), _patch_runtime(payload, captured=captured):
        resp = client.post(
            "/v1/sessions/s-1/workspace/tree",
            headers=_AUTH,
            json={
                "runtime_endpoint": "http://runtime-x:3000",
                "agent_id": "agent-1",
                "path": "/src",
                "include_hidden": True,
            },
        )
    assert resp.status_code == 200
    assert resp.json() == payload
    assert captured["url"] == "http://runtime-x:3000/workspace/tree"
    assert captured["params"] == {
        "session_id": "s-1",
        "path": "/src",
        "include_hidden": "1",
        "agent_id": "agent-1",
    }


def test_tree_omits_agent_id_when_missing(client):
    """Supervisor lets the runtime enforce agent_id requirements; it doesn't
    second-guess when the caller leaves it null (root listings don't need it)."""
    captured: dict = {}
    with _patch_auth(), _patch_runtime({"path": "/", "entries": []}, captured=captured):
        resp = client.post(
            "/v1/sessions/s-1/workspace/tree",
            headers=_AUTH,
            json={"path": "/"},
        )
    assert resp.status_code == 200
    assert "agent_id" not in captured["params"]


def test_tree_propagates_runtime_4xx(client):
    err = {"error": "path escapes session workspace", "code": "invalid_path"}
    with _patch_auth(), _patch_runtime(err, status=400):
        resp = client.post(
            "/v1/sessions/s-1/workspace/tree",
            headers=_AUTH,
            json={"path": "../etc"},
        )
    assert resp.status_code == 400
    assert resp.json() == err


def test_tree_falls_back_to_default_runtime(client):
    captured: dict = {}
    with _patch_auth(), _patch_runtime({"path": "/", "entries": []}, captured=captured):
        resp = client.post(
            "/v1/sessions/s-1/workspace/tree", headers=_AUTH, json={"path": "/"},
        )
    assert resp.status_code == 200
    from app.config import settings
    assert captured["url"].startswith(settings.supervisor_default_runtime_endpoint)


def test_file_proxies_payload(client):
    captured: dict = {}
    payload = {
        "path": "/hello.txt",
        "content": "hello",
        "encoding": "utf8",
        "size": 5,
        "mtime": 1700000000000,
        "isBinary": False,
        "truncated": False,
    }
    with _patch_auth(), _patch_runtime(payload, captured=captured):
        resp = client.post(
            "/v1/sessions/s-1/workspace/file",
            headers=_AUTH,
            json={"agent_id": "agent-1", "path": "/hello.txt"},
        )
    assert resp.status_code == 200
    assert resp.json() == payload
    assert captured["params"] == {
        "session_id": "s-1",
        "path": "/hello.txt",
        "agent_id": "agent-1",
    }


def test_file_requires_path(client):
    with _patch_auth():
        resp = client.post(
            "/v1/sessions/s-1/workspace/file", headers=_AUTH, json={},
        )
    assert resp.status_code == 422


def test_runtime_unreachable_returns_502(client):
    class _BrokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *a, **kw):
            import httpx
            raise httpx.ConnectError("boom")

    with _patch_auth(), patch("httpx.AsyncClient", return_value=_BrokenClient()):
        resp = client.post(
            "/v1/sessions/s-1/workspace/tree",
            headers=_AUTH,
            json={"path": "/"},
        )
    assert resp.status_code == 502
    assert resp.json() == {"error": "runtime unreachable"}

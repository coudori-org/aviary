"""Worker authentication path on /v1/sessions/{sid}/message.

X-Aviary-Worker-Key + body.on_behalf_of_sub lets the Temporal workflow
worker call supervisor for an owner who isn't interactively present. The
supervisor trusts the provided sub (since the key is a shared secret) and
looks up Vault credentials as if that user had authenticated.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

WORKER_SECRET = "test-worker-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.worker_shared_secret", WORKER_SECRET, raising=False
    )
    from app.main import app
    return TestClient(app)


class _FakeSSEResponse:
    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return "\n".join(self._lines).encode()


class _FakeStreamCtx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *_):
        return False


class _FakeClient:
    def __init__(self, resp, captured=None):
        self._resp = resp
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def stream(self, method, url, **kwargs):
        if self._captured is not None:
            self._captured["url"] = url
            self._captured["json"] = kwargs.get("json")
        return _FakeStreamCtx(self._resp)


_AGENT_CONFIG = {
    "agent_id": "a1",
    "runtime_endpoint": None,
    "model_config": {"backend": "anthropic", "model": "claude-sonnet"},
    "instruction": "",
    "tools": [],
    "mcp_servers": {},
}


def _body(**extra):
    b = {
        "session_id": "s1",
        "content_parts": [{"text": "hi"}],
        "agent_config": dict(_AGENT_CONFIG),
    }
    b.update(extra)
    return b


def _redis_patches():
    return [
        patch("app.routers.agents.redis_client.append_stream_chunk", new_callable=AsyncMock),
        patch("app.routers.agents.redis_client.publish_event", new_callable=AsyncMock),
        patch("app.routers.agents.redis_client.set_stream_status", new_callable=AsyncMock),
        patch("app.routers.agents.redis_client.set_session_status", new_callable=AsyncMock),
        patch("app.routers.agents.redis_client.set_session_latest_stream", new_callable=AsyncMock),
        patch(
            "app.routers.agents.redis_client.get_stream_chunks",
            new_callable=AsyncMock, return_value=[],
        ),
    ]


def test_worker_key_missing_on_behalf_of_sub_returns_400(client):
    resp = client.post(
        "/v1/sessions/s1/message",
        headers={"X-Aviary-Worker-Key": WORKER_SECRET},
        json=_body(),
    )
    assert resp.status_code == 400


def test_worker_key_invalid_returns_401(client):
    resp = client.post(
        "/v1/sessions/s1/message",
        headers={"X-Aviary-Worker-Key": "wrong"},
        json=_body(on_behalf_of_sub="owner-1"),
    )
    assert resp.status_code == 401


def test_worker_path_injects_sub_and_credentials_without_user_token(client):
    lines = [
        'data: {"type": "query_started"}',
        'data: {"type": "chunk", "content": "ok"}',
    ]
    captured: dict = {}

    with patch(
        "httpx.AsyncClient",
        return_value=_FakeClient(_FakeSSEResponse(lines), captured=captured),
    ), patch(
        "app.routers.agents.fetch_user_credentials",
        AsyncMock(return_value={"github_token": "ghp_owner"}),
    ):
        with _redis_patches()[0], _redis_patches()[1], _redis_patches()[2], \
             _redis_patches()[3], _redis_patches()[4], _redis_patches()[5]:
            resp = client.post(
                "/v1/sessions/s1/message",
                headers={"X-Aviary-Worker-Key": WORKER_SECRET},
                json=_body(on_behalf_of_sub="owner-42"),
            )

    assert resp.status_code == 200, resp.text
    forwarded = captured["json"]
    # Worker-auth body field must never leak to the runtime
    assert "on_behalf_of_sub" not in forwarded
    agent = forwarded["agent_config"]
    assert agent["user_external_id"] == "owner-42"
    assert agent["credentials"] == {"github_token": "ghp_owner"}
    # No user_token on worker path
    assert "user_token" not in agent


def test_jwt_path_ignores_on_behalf_of_sub_in_body(client):
    """Only the worker path can set the authenticated sub — a JWT caller
    cannot impersonate another user by adding on_behalf_of_sub to the body.
    """
    from app.auth.oidc import TokenClaims
    lines = ['data: {"type": "query_started"}']
    captured: dict = {}

    with patch(
        "app.auth.dependencies.validate_token",
        AsyncMock(return_value=TokenClaims(sub="real-user", email="u@t", display_name="u")),
    ), patch(
        "httpx.AsyncClient",
        return_value=_FakeClient(_FakeSSEResponse(lines), captured=captured),
    ), patch(
        "app.routers.agents.fetch_user_credentials",
        AsyncMock(return_value={}),
    ):
        with _redis_patches()[0], _redis_patches()[1], _redis_patches()[2], \
             _redis_patches()[3], _redis_patches()[4], _redis_patches()[5]:
            resp = client.post(
                "/v1/sessions/s1/message",
                headers={"Authorization": "Bearer jwt"},
                json=_body(on_behalf_of_sub="attacker-target"),
            )

    assert resp.status_code == 200, resp.text
    forwarded = captured["json"]
    assert forwarded["agent_config"]["user_external_id"] == "real-user"
    assert "on_behalf_of_sub" not in forwarded

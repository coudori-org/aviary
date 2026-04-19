"""GET /api/sessions/{sid}/workspace/{tree,file} — owner check + proxy."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _create_session(client: AsyncClient) -> tuple[str, str]:
    agent_resp = await client.post("/api/agents", json={
        "name": "Chat Agent",
        "slug": "chat-agent",
        "instruction": "Be helpful.",
        "model_config": {"backend": "dummy-backend", "model": "dummy-model"},
    })
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    session_resp = await client.post(f"/api/agents/{agent_id}/sessions", json={})
    assert session_resp.status_code == 201
    return agent_id, session_resp.json()["id"]


@pytest.mark.asyncio
async def test_tree_owner_sees_runtime_payload(user1_client: AsyncClient):
    agent_id, session_id = await _create_session(user1_client)

    payload = {"path": "/", "entries": [{"name": "README.md", "type": "file"}]}
    mock = AsyncMock(return_value=(200, payload))
    with patch("app.services.agent_supervisor.fetch_workspace_tree", mock):
        resp = await user1_client.get(f"/api/sessions/{session_id}/workspace/tree")

    assert resp.status_code == 200
    assert resp.json() == payload
    assert mock.await_count == 1
    args, _ = mock.await_args
    # Positional: (session_id, user_token, runtime_endpoint, agent_id, path, include_hidden)
    assert args[0] == session_id
    assert args[3] == agent_id
    assert args[4] == "/"
    assert args[5] is False


@pytest.mark.asyncio
async def test_tree_forwards_query_params(user1_client: AsyncClient):
    agent_id, session_id = await _create_session(user1_client)

    mock = AsyncMock(return_value=(200, {"path": "/src", "entries": []}))
    with patch("app.services.agent_supervisor.fetch_workspace_tree", mock):
        resp = await user1_client.get(
            f"/api/sessions/{session_id}/workspace/tree",
            params={"path": "/src", "include_hidden": "true"},
        )
    assert resp.status_code == 200
    args, _ = mock.await_args
    assert args[3] == agent_id
    assert args[4] == "/src"
    assert args[5] is True


@pytest.mark.asyncio
async def test_tree_rejects_non_owner(user1_client: AsyncClient, user3_client: AsyncClient):
    _, session_id = await _create_session(user1_client)

    mock = AsyncMock(return_value=(200, {"path": "/", "entries": []}))
    with patch("app.services.agent_supervisor.fetch_workspace_tree", mock):
        resp = await user3_client.get(f"/api/sessions/{session_id}/workspace/tree")

    assert resp.status_code == 403
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_tree_404_for_unknown_session(user1_client: AsyncClient):
    mock = AsyncMock()
    with patch("app.services.agent_supervisor.fetch_workspace_tree", mock):
        resp = await user1_client.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000/workspace/tree",
        )
    assert resp.status_code == 404
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_tree_propagates_supervisor_error_status(user1_client: AsyncClient):
    _, session_id = await _create_session(user1_client)

    mock = AsyncMock(return_value=(400, {"error": "path escapes session workspace"}))
    with patch("app.services.agent_supervisor.fetch_workspace_tree", mock):
        resp = await user1_client.get(
            f"/api/sessions/{session_id}/workspace/tree",
            params={"path": "../etc"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"] == "path escapes session workspace"


@pytest.mark.asyncio
async def test_file_owner_sees_payload(user1_client: AsyncClient):
    _, session_id = await _create_session(user1_client)

    payload = {
        "path": "/hello.txt", "content": "hi", "encoding": "utf8",
        "size": 2, "mtime": 1700000000000, "isBinary": False, "truncated": False,
    }
    mock = AsyncMock(return_value=(200, payload))
    with patch("app.services.agent_supervisor.fetch_workspace_file", mock):
        resp = await user1_client.get(
            f"/api/sessions/{session_id}/workspace/file",
            params={"path": "/hello.txt"},
        )

    assert resp.status_code == 200
    assert resp.json() == payload


@pytest.mark.asyncio
async def test_file_requires_path_query(user1_client: AsyncClient):
    _, session_id = await _create_session(user1_client)

    mock = AsyncMock()
    with patch("app.services.agent_supervisor.fetch_workspace_file", mock):
        resp = await user1_client.get(f"/api/sessions/{session_id}/workspace/file")
    # FastAPI rejects missing required query param as 422.
    assert resp.status_code == 422
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_file_non_owner_blocked(user1_client: AsyncClient, user3_client: AsyncClient):
    _, session_id = await _create_session(user1_client)

    mock = AsyncMock()
    with patch("app.services.agent_supervisor.fetch_workspace_file", mock):
        resp = await user3_client.get(
            f"/api/sessions/{session_id}/workspace/file",
            params={"path": "/hello.txt"},
        )
    assert resp.status_code == 403
    assert mock.await_count == 0

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _create_agent(client: AsyncClient) -> str:
    resp = await client.post("/api/agents", json={
        "name": "Chat Agent",
        "slug": "chat-agent",
        "instruction": "Be helpful.",
        "model_config": {"backend": "dummy-backend", "model": "dummy-model"},
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session(user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client)

    resp = await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == agent_id
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_sessions(user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client)

    await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})

    resp = await user1_client.get(f"/api/agents/{agent_id}/sessions")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_get_session_with_messages(user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client)

    session_resp = await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    session_id = session_resp.json()["id"]

    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_non_owner_cannot_access_session(user1_client: AsyncClient, user3_client: AsyncClient):
    agent_id = await _create_agent(user1_client)
    session_resp = await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    session_id = session_resp.json()["id"]

    resp = await user3_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_session(user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client)

    session_resp = await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    session_id = session_resp.json()["id"]

    with patch("app.services.agent_supervisor.cleanup_session", new_callable=AsyncMock):
        resp = await user1_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204

    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 404

import pytest
from httpx import AsyncClient


async def _create_public_agent(client: AsyncClient) -> str:
    resp = await client.post("/api/agents", json={
        "name": "Chat Agent",
        "slug": "chat-agent",
        "instruction": "Be helpful.",
        "visibility": "public",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_session(admin_client: AsyncClient):
    agent_id = await _create_public_agent(admin_client)

    resp = await admin_client.post(f"/api/agents/{agent_id}/sessions", json={
        "type": "private",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == agent_id
    assert data["type"] == "private"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_sessions(admin_client: AsyncClient):
    agent_id = await _create_public_agent(admin_client)

    await admin_client.post(f"/api/agents/{agent_id}/sessions", json={"type": "private"})
    await admin_client.post(f"/api/agents/{agent_id}/sessions", json={"type": "private"})

    resp = await admin_client.get(f"/api/agents/{agent_id}/sessions")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_get_session_with_messages(admin_client: AsyncClient):
    agent_id = await _create_public_agent(admin_client)

    session_resp = await admin_client.post(f"/api/agents/{agent_id}/sessions", json={"type": "private"})
    session_id = session_resp.json()["id"]

    resp = await admin_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"]["id"] == session_id
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_non_participant_cannot_access_session(admin_client: AsyncClient, user2_client: AsyncClient):
    agent_id = await _create_public_agent(admin_client)

    session_resp = await admin_client.post(f"/api/agents/{agent_id}/sessions", json={"type": "private"})
    session_id = session_resp.json()["id"]

    # user2 is not a participant
    resp = await user2_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_session(admin_client: AsyncClient):
    agent_id = await _create_public_agent(admin_client)

    session_resp = await admin_client.post(f"/api/agents/{agent_id}/sessions", json={"type": "private"})
    session_id = session_resp.json()["id"]

    resp = await admin_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204

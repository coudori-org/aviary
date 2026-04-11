import pytest
from httpx import AsyncClient

_MODEL_CONFIG = {"backend": "dummy-backend", "model": "dummy-model"}


@pytest.mark.asyncio
async def test_create_agent(user1_client: AsyncClient):
    resp = await user1_client.post("/api/agents", json={
        "name": "Test Agent",
        "slug": "test-agent",
        "description": "A test agent",
        "instruction": "You are a helpful assistant.",
        "model_config": _MODEL_CONFIG,
        "tools": ["read_file", "write_file"],
        "visibility": "private",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Test Agent"
    assert data["slug"] == "test-agent"
    assert data["visibility"] == "private"
    assert data["model_config"]["backend"] == "dummy-backend"


@pytest.mark.asyncio
async def test_create_agent_duplicate_slug(user1_client: AsyncClient):
    await user1_client.post("/api/agents", json={
        "name": "Agent A",
        "slug": "dup-slug",
        "instruction": "Be helpful.",
        "model_config": _MODEL_CONFIG,
    })
    resp = await user1_client.post("/api/agents", json={
        "name": "Agent B",
        "slug": "dup-slug",
        "instruction": "Be helpful too.",
        "model_config": _MODEL_CONFIG,
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_agents(user1_client: AsyncClient):
    # Create 2 agents
    await user1_client.post("/api/agents", json={
        "name": "Agent 1", "slug": "agent-1", "instruction": "Hello",
        "model_config": _MODEL_CONFIG,
    })
    await user1_client.post("/api/agents", json={
        "name": "Agent 2", "slug": "agent-2", "instruction": "World",
        "model_config": _MODEL_CONFIG,
    })

    resp = await user1_client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_agent(user1_client: AsyncClient):
    create_resp = await user1_client.post("/api/agents", json={
        "name": "Detail Agent", "slug": "detail-agent", "instruction": "Help me.",
        "model_config": _MODEL_CONFIG,
    })
    agent_id = create_resp.json()["id"]

    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Agent"


@pytest.mark.asyncio
async def test_update_agent(user1_client: AsyncClient):
    create_resp = await user1_client.post("/api/agents", json={
        "name": "Old Name", "slug": "update-test", "instruction": "V1",
        "model_config": _MODEL_CONFIG,
    })
    agent_id = create_resp.json()["id"]

    resp = await user1_client.put(f"/api/agents/{agent_id}", json={
        "name": "New Name",
        "instruction": "V2",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["instruction"] == "V2"


@pytest.mark.asyncio
async def test_delete_agent(user1_client: AsyncClient):
    create_resp = await user1_client.post("/api/agents", json={
        "name": "To Delete", "slug": "delete-me", "instruction": "Bye",
        "model_config": _MODEL_CONFIG,
    })
    agent_id = create_resp.json()["id"]

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    # Agent with no sessions is hard-deleted
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404

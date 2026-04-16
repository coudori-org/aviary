"""Tests for admin agent CRUD endpoints."""

import pytest
from httpx import AsyncClient

from aviary_shared.db.models import Agent


@pytest.mark.asyncio
async def test_list_agents_empty(client: AsyncClient):
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_agents(client: AsyncClient, seed_agent: Agent):
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(seed_agent.id)


@pytest.mark.asyncio
async def test_get_agent(client: AsyncClient, seed_agent: Agent):
    resp = await client.get(f"/api/agents/{seed_agent.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Agent"
    assert data["runtime_endpoint"] is None


@pytest.mark.asyncio
async def test_get_agent_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_agent(client: AsyncClient, seed_agent: Agent):
    resp = await client.put(f"/api/agents/{seed_agent.id}", json={
        "name": "Updated Agent",
        "instruction": "Be very helpful.",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Agent"
    assert data["instruction"] == "Be very helpful."


@pytest.mark.asyncio
async def test_update_agent_runtime_endpoint(client: AsyncClient, seed_agent: Agent):
    resp = await client.put(f"/api/agents/{seed_agent.id}", json={
        "runtime_endpoint": "http://aviary-env-custom.agents.svc:3000",
    })
    assert resp.status_code == 200
    assert resp.json()["runtime_endpoint"] == "http://aviary-env-custom.agents.svc:3000"

    # Clearing by empty string reverts to default.
    resp = await client.put(f"/api/agents/{seed_agent.id}", json={"runtime_endpoint": ""})
    assert resp.status_code == 200
    assert resp.json()["runtime_endpoint"] is None


@pytest.mark.asyncio
async def test_delete_agent(client: AsyncClient, seed_agent: Agent):
    resp = await client.delete(f"/api/agents/{seed_agent.id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/agents/{seed_agent.id}")
    assert resp.status_code == 404

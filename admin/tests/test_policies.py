"""Tests for admin policy management endpoints."""

import pytest
from httpx import AsyncClient

from aviary_shared.db.models import Agent


@pytest.mark.asyncio
async def test_get_policy_defaults(client: AsyncClient, seed_agent: Agent):
    resp = await client.get(f"/api/agents/{seed_agent.id}/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == str(seed_agent.id)
    assert data["policy"] == {}
    assert data["min_pods"] == 0
    assert data["max_pods"] == 3
    assert data["service_account_id"] is None


@pytest.mark.asyncio
async def test_get_policy_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/policy")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_policy_scaling_bounds(client: AsyncClient, seed_agent: Agent):
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "min_pods": 2, "max_pods": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_pods"] == 2
    assert data["max_pods"] == 5

    resp = await client.get(f"/api/agents/{seed_agent.id}/policy")
    assert resp.json()["min_pods"] == 2
    assert resp.json()["max_pods"] == 5


@pytest.mark.asyncio
async def test_update_resource_limits_via_policy_rules(client: AsyncClient, seed_agent: Agent):
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "maxMemoryPerSession": "8Gi",
            "maxCpuPerSession": "8",
            "containerImage": "custom:latest",
        },
    })
    assert resp.status_code == 200
    policy = resp.json()["policy"]
    assert policy["maxMemoryPerSession"] == "8Gi"
    assert policy["maxCpuPerSession"] == "8"
    assert policy["containerImage"] == "custom:latest"


@pytest.mark.asyncio
async def test_force_sync_identity(client: AsyncClient, seed_agent: Agent):
    resp = await client.post(f"/api/agents/{seed_agent.id}/policy/sync")
    assert resp.status_code == 200
    assert resp.json()["synced"]["identity"] is True

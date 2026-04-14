"""Tests for admin deployment management endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from aviary_shared.db.models import Agent


@pytest.mark.asyncio
async def test_get_deployment_status_no_namespace(client: AsyncClient, seed_agent: Agent):
    """Agent without an active deployment returns zero replicas."""
    resp = await client.get(f"/api/agents/{seed_agent.id}/deployment")
    assert resp.status_code == 200
    data = resp.json()
    assert data["replicas"] == 0
    assert data["ready_replicas"] == 0


@pytest.mark.asyncio
async def test_get_deployment_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/deployment")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_activate_agent(client: AsyncClient, seed_agent: Agent):
    """Activate provisions the agent via supervisor."""
    with patch("app.services.supervisor_client.ensure_agent", new_callable=AsyncMock) as mock_ensure, \
         patch("app.services.supervisor_client.unbind_identity", new_callable=AsyncMock):
        resp = await client.post(f"/api/agents/{seed_agent.id}/activate")

    assert resp.status_code == 200
    assert resp.json()["status"] == "activated"
    mock_ensure.assert_called_once()


@pytest.mark.asyncio
async def test_activate_agent_not_found(client: AsyncClient):
    resp = await client.post("/api/agents/00000000-0000-0000-0000-000000000000/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_agent(client: AsyncClient, seed_agent: Agent):
    with patch("app.services.supervisor_client.ensure_agent", new_callable=AsyncMock), \
         patch("app.services.supervisor_client.unbind_identity", new_callable=AsyncMock):
        await client.post(f"/api/agents/{seed_agent.id}/activate")

    with patch("app.services.supervisor_client.scale_to_zero", new_callable=AsyncMock) as mock_scale:
        resp = await client.post(f"/api/agents/{seed_agent.id}/deactivate")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"
    mock_scale.assert_called_once()


@pytest.mark.asyncio
async def test_deploy_triggers_restart(client: AsyncClient, seed_agent: Agent):
    with patch("app.services.supervisor_client.ensure_agent", new_callable=AsyncMock), \
         patch("app.services.supervisor_client.unbind_identity", new_callable=AsyncMock):
        await client.post(f"/api/agents/{seed_agent.id}/activate")

    with patch("app.services.supervisor_client.rolling_restart", new_callable=AsyncMock) as mock_restart:
        resp = await client.post(f"/api/agents/{seed_agent.id}/deploy")

    assert resp.status_code == 200
    assert resp.json()["status"] == "deploying"
    mock_restart.assert_called_once()


@pytest.mark.asyncio
async def test_scale_agent(client: AsyncClient, seed_agent: Agent):
    with patch("app.services.supervisor_client.ensure_agent", new_callable=AsyncMock), \
         patch("app.services.supervisor_client.unbind_identity", new_callable=AsyncMock):
        await client.post(f"/api/agents/{seed_agent.id}/activate")

    with patch("app.services.supervisor_client.get_deployment_status", new_callable=AsyncMock,
               return_value={"exists": True, "replicas": 1, "ready_replicas": 1}), \
         patch("app.services.supervisor_client.scale_deployment", new_callable=AsyncMock) as mock_scale:
        resp = await client.patch(f"/api/agents/{seed_agent.id}/scale", json={
            "replicas": 3, "min_pods": 2, "max_pods": 5,
        })

    assert resp.status_code == 200
    assert resp.json()["replicas"] == 3
    mock_scale.assert_called_once_with(str(seed_agent.id), 3)

    resp = await client.get(f"/api/agents/{seed_agent.id}/policy")
    assert resp.json()["min_pods"] == 2
    assert resp.json()["max_pods"] == 5


@pytest.mark.asyncio
async def test_scale_agent_without_namespace(client: AsyncClient, seed_agent: Agent):
    """Scaling without an active deployment updates DB but skips supervisor call."""
    with patch("app.services.supervisor_client.scale_deployment", new_callable=AsyncMock) as mock_scale:
        resp = await client.patch(f"/api/agents/{seed_agent.id}/scale", json={
            "replicas": 2, "min_pods": 1, "max_pods": 4,
        })

    assert resp.status_code == 200
    mock_scale.assert_not_called()

    resp = await client.get(f"/api/agents/{seed_agent.id}/policy")
    assert resp.json()["min_pods"] == 1
    assert resp.json()["max_pods"] == 4

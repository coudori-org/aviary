"""Tests for admin policy management endpoints."""

from unittest.mock import AsyncMock, patch

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
    assert data["pod_strategy"] == "lazy"
    assert data["min_pods"] == 1
    assert data["max_pods"] == 3


@pytest.mark.asyncio
async def test_get_policy_not_found(client: AsyncClient):
    resp = await client.get("/api/agents/00000000-0000-0000-0000-000000000000/policy")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_policy_with_cidr_egress(client: AsyncClient, seed_agent: Agent):
    """Update policy with CIDR-based egress rules."""
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "allowedEgress": [
                {"name": "GitHub API", "cidr": "140.82.112.0/20", "ports": [{"port": 443, "protocol": "TCP"}]},
                {"name": "Internal", "cidr": "10.0.0.0/8"},
            ],
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["policy"]["allowedEgress"]) == 2
    assert data["policy"]["allowedEgress"][0]["cidr"] == "140.82.112.0/20"
    assert data["policy"]["allowedEgress"][1]["cidr"] == "10.0.0.0/8"


@pytest.mark.asyncio
async def test_update_policy_with_domain_egress(client: AsyncClient, seed_agent: Agent):
    """Update policy with domain-based egress rules."""
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "allowedEgress": [
                {"name": "GitHub", "domain": "*.github.com"},
                {"name": "S3", "domain": "s3.amazonaws.com", "ports": [{"port": 443}]},
            ],
        },
    })
    assert resp.status_code == 200
    rules = resp.json()["policy"]["allowedEgress"]
    assert rules[0]["domain"] == "*.github.com"
    assert rules[1]["domain"] == "s3.amazonaws.com"


@pytest.mark.asyncio
async def test_update_policy_mixed_egress(client: AsyncClient, seed_agent: Agent):
    """CIDR and domain rules can be mixed in the same policy."""
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "allowedEgress": [
                {"name": "Internal Net", "cidr": "10.0.0.0/8"},
                {"name": "GitHub", "domain": "*.github.com"},
            ],
        },
    })
    assert resp.status_code == 200
    rules = resp.json()["policy"]["allowedEgress"]
    assert rules[0]["cidr"] == "10.0.0.0/8"
    assert rules[1]["domain"] == "*.github.com"


@pytest.mark.asyncio
async def test_update_policy_clears_egress(client: AsyncClient, seed_agent: Agent):
    """Setting empty allowedEgress clears all rules."""
    # First set some rules
    await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "allowedEgress": [{"name": "test", "domain": "example.com"}],
        },
    })

    # Then clear
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {"allowedEgress": []},
    })
    assert resp.status_code == 200
    assert resp.json()["policy"]["allowedEgress"] == []


@pytest.mark.asyncio
async def test_update_pod_strategy(client: AsyncClient, seed_agent: Agent):
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "pod_strategy": "eager",
        "min_pods": 2,
        "max_pods": 5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["pod_strategy"] == "eager"
    assert data["min_pods"] == 2
    assert data["max_pods"] == 5

    # Verify persisted
    resp = await client.get(f"/api/agents/{seed_agent.id}/policy")
    assert resp.json()["pod_strategy"] == "eager"
    assert resp.json()["min_pods"] == 2
    assert resp.json()["max_pods"] == 5


@pytest.mark.asyncio
async def test_update_resource_limits(client: AsyncClient, seed_agent: Agent):
    """Update resource limits via policy dict."""
    resp = await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {
            "maxMemoryPerSession": "8Gi",
            "maxCpuPerSession": "8",
            "maxConcurrentSessions": 50,
        },
    })
    assert resp.status_code == 200
    policy = resp.json()["policy"]
    assert policy["maxMemoryPerSession"] == "8Gi"
    assert policy["maxCpuPerSession"] == "8"
    assert policy["maxConcurrentSessions"] == 50


@pytest.mark.asyncio
async def test_force_sync_policy_without_namespace(client: AsyncClient, seed_agent: Agent):
    """Force sync when agent has no namespace — K8s sync fails gracefully."""
    # Set a policy first
    await client.put(f"/api/agents/{seed_agent.id}/policy", json={
        "policy": {"allowedEgress": [{"name": "test", "domain": "example.com"}]},
    })

    resp = await client.post(f"/api/agents/{seed_agent.id}/policy/sync")

    assert resp.status_code == 200
    data = resp.json()
    # No sg_ref in policy → unbind_identity is attempted (mocked, returns success).
    assert data["synced"]["identity"] is True

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_agent(admin_client: AsyncClient):
    resp = await admin_client.post("/api/agents", json={
        "name": "Test Agent",
        "slug": "test-agent",
        "description": "A test agent",
        "instruction": "You are a helpful assistant.",
        "model_config": {
            "backend": "claude",
            "model": "default",
            "temperature": 0.7,
            "maxTokens": 8192,
        },
        "tools": ["read_file", "write_file"],
        "visibility": "private",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Test Agent"
    assert data["slug"] == "test-agent"
    assert data["visibility"] == "private"
    assert data["model_config"]["backend"] == "claude"


@pytest.mark.asyncio
async def test_create_agent_duplicate_slug(admin_client: AsyncClient):
    await admin_client.post("/api/agents", json={
        "name": "Agent A",
        "slug": "dup-slug",
        "instruction": "Be helpful.",
    })
    resp = await admin_client.post("/api/agents", json={
        "name": "Agent B",
        "slug": "dup-slug",
        "instruction": "Be helpful too.",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_agents(admin_client: AsyncClient):
    # Create 2 agents
    await admin_client.post("/api/agents", json={
        "name": "Agent 1", "slug": "agent-1", "instruction": "Hello"
    })
    await admin_client.post("/api/agents", json={
        "name": "Agent 2", "slug": "agent-2", "instruction": "World"
    })

    resp = await admin_client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_agent(admin_client: AsyncClient):
    create_resp = await admin_client.post("/api/agents", json={
        "name": "Detail Agent", "slug": "detail-agent", "instruction": "Help me."
    })
    agent_id = create_resp.json()["id"]

    resp = await admin_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Detail Agent"


@pytest.mark.asyncio
async def test_update_agent(admin_client: AsyncClient):
    create_resp = await admin_client.post("/api/agents", json={
        "name": "Old Name", "slug": "update-test", "instruction": "V1"
    })
    agent_id = create_resp.json()["id"]

    resp = await admin_client.put(f"/api/agents/{agent_id}", json={
        "name": "New Name",
        "instruction": "V2",
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["instruction"] == "V2"


@pytest.mark.asyncio
async def test_delete_agent(admin_client: AsyncClient):
    create_resp = await admin_client.post("/api/agents", json={
        "name": "To Delete", "slug": "delete-me", "instruction": "Bye"
    })
    agent_id = create_resp.json()["id"]

    resp = await admin_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    # Should not appear in list anymore
    resp = await admin_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_with_cidr_egress(admin_client: AsyncClient):
    resp = await admin_client.post("/api/agents", json={
        "name": "CIDR Egress Agent",
        "slug": "cidr-egress-agent",
        "instruction": "Help me.",
        "policy": {
            "allowedEgress": [
                {"name": "GitHub API", "cidr": "140.82.112.0/20", "ports": [{"port": 443, "protocol": "TCP"}]},
                {"name": "Custom Service", "cidr": "10.0.0.0/8"},
            ],
        },
    })
    assert resp.status_code == 201, resp.text
    policy = resp.json()["policy"]
    assert len(policy["allowedEgress"]) == 2
    assert policy["allowedEgress"][0]["cidr"] == "140.82.112.0/20"
    assert policy["allowedEgress"][1]["ports"] == []


@pytest.mark.asyncio
async def test_create_agent_with_domain_egress(admin_client: AsyncClient):
    resp = await admin_client.post("/api/agents", json={
        "name": "Domain Egress Agent",
        "slug": "domain-egress-agent",
        "instruction": "Help me.",
        "policy": {
            "allowedEgress": [
                {"name": "GitHub", "domain": "*.github.com"},
                {"name": "S3", "domain": "s3.amazonaws.com", "ports": [{"port": 443}]},
            ],
        },
    })
    assert resp.status_code == 201, resp.text
    policy = resp.json()["policy"]
    assert len(policy["allowedEgress"]) == 2
    assert policy["allowedEgress"][0]["domain"] == "*.github.com"
    assert policy["allowedEgress"][0]["cidr"] is None
    assert policy["allowedEgress"][1]["domain"] == "s3.amazonaws.com"


@pytest.mark.asyncio
async def test_create_agent_mixed_egress(admin_client: AsyncClient):
    """CIDR and domain rules can be mixed in the same policy."""
    resp = await admin_client.post("/api/agents", json={
        "name": "Mixed Egress Agent",
        "slug": "mixed-egress-agent",
        "instruction": "Help me.",
        "policy": {
            "allowedEgress": [
                {"name": "Internal Net", "cidr": "10.0.0.0/8"},
                {"name": "GitHub", "domain": "*.github.com"},
            ],
        },
    })
    assert resp.status_code == 201, resp.text
    rules = resp.json()["policy"]["allowedEgress"]
    assert rules[0]["cidr"] == "10.0.0.0/8"
    assert rules[1]["domain"] == "*.github.com"


@pytest.mark.asyncio
async def test_update_agent_egress_policy(admin_client: AsyncClient):
    create_resp = await admin_client.post("/api/agents", json={
        "name": "Policy Agent", "slug": "policy-agent", "instruction": "V1"
    })
    agent_id = create_resp.json()["id"]
    assert create_resp.json()["policy"]["allowedEgress"] == []

    # Add egress rules (both types)
    resp = await admin_client.put(f"/api/agents/{agent_id}", json={
        "policy": {
            "allowedEgress": [
                {"name": "S3", "cidr": "52.216.0.0/15", "ports": [{"port": 443}]},
                {"name": "NPM", "domain": "registry.npmjs.org"},
            ],
        },
    })
    assert resp.status_code == 200
    assert len(resp.json()["policy"]["allowedEgress"]) == 2

    # Remove all egress rules
    resp = await admin_client.put(f"/api/agents/{agent_id}", json={
        "policy": {"allowedEgress": []},
    })
    assert resp.status_code == 200
    assert resp.json()["policy"]["allowedEgress"] == []


@pytest.mark.asyncio
async def test_create_agent_invalid_egress_cidr(admin_client: AsyncClient):
    resp = await admin_client.post("/api/agents", json={
        "name": "Bad CIDR",
        "slug": "bad-cidr",
        "instruction": "Help",
        "policy": {
            "allowedEgress": [{"name": "Invalid", "cidr": "not-a-cidr"}],
        },
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_agent_egress_requires_cidr_or_domain(admin_client: AsyncClient):
    """Must provide exactly one of cidr or domain."""
    # Neither
    resp = await admin_client.post("/api/agents", json={
        "name": "No Target",
        "slug": "no-target",
        "instruction": "Help",
        "policy": {
            "allowedEgress": [{"name": "Empty"}],
        },
    })
    assert resp.status_code == 422

    # Both
    resp = await admin_client.post("/api/agents", json={
        "name": "Both Target",
        "slug": "both-target",
        "instruction": "Help",
        "policy": {
            "allowedEgress": [{"name": "Both", "cidr": "10.0.0.0/8", "domain": "example.com"}],
        },
    })
    assert resp.status_code == 422

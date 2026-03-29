import pytest
from httpx import AsyncClient


async def _create_agent(client: AsyncClient, slug: str, visibility: str = "private") -> str:
    resp = await client.post("/api/agents", json={
        "name": f"Agent {slug}",
        "slug": slug,
        "instruction": "Help",
        "visibility": visibility,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_private_agent_invisible_to_others(admin_client: AsyncClient, user1_client: AsyncClient):
    agent_id = await _create_agent(admin_client, "private-agent", "private")

    # user1 should not see the private agent
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_public_agent_visible_to_all(admin_client: AsyncClient, user1_client: AsyncClient):
    agent_id = await _create_agent(admin_client, "public-agent", "public")

    # user1 can see a public agent
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_grant_acl_allows_access(admin_client: AsyncClient, user1_client: AsyncClient):
    agent_id = await _create_agent(admin_client, "acl-test", "private")

    # user1 cannot access yet
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 403

    # Get user1's ID
    me_resp = await user1_client.get("/api/auth/me")
    user1_id = me_resp.json()["id"]

    # Admin grants user role
    acl_resp = await admin_client.post(f"/api/agents/{agent_id}/acl", json={
        "user_id": user1_id,
        "role": "user",
    })
    assert acl_resp.status_code == 201

    # Now user1 can access
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_acl(user1_client: AsyncClient, admin_client: AsyncClient):
    agent_id = await _create_agent(admin_client, "no-manage", "public")

    # user1 has implicit 'user' role on public agent, but cannot manage ACL
    resp = await user1_client.post(f"/api/agents/{agent_id}/acl", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "role": "user",
    })
    assert resp.status_code == 403

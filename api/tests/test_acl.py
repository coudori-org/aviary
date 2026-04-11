import pytest
from httpx import AsyncClient


_TEST_MODEL_CONFIG = {"backend": "dummy-backend", "model": "dummy-model"}


async def _create_agent(client: AsyncClient, slug: str, visibility: str = "private") -> str:
    resp = await client.post("/api/agents", json={
        "name": f"Agent {slug}",
        "slug": slug,
        "instruction": "Help",
        "model_config": _TEST_MODEL_CONFIG,
        "visibility": visibility,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_private_agent_invisible_to_others(user1_client: AsyncClient, user2_client: AsyncClient):
    agent_id = await _create_agent(user1_client, "private-agent", "private")

    # user2 should not see the private agent
    resp = await user2_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_public_agent_visible_to_all(user1_client: AsyncClient, user2_client: AsyncClient):
    agent_id = await _create_agent(user1_client, "public-agent", "public")

    # user2 can see a public agent
    resp = await user2_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_grant_acl_allows_access(user1_client: AsyncClient, user2_client: AsyncClient):
    agent_id = await _create_agent(user1_client, "acl-test", "private")

    # user2 cannot access yet
    resp = await user2_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 403

    # Get user2's ID
    me_resp = await user2_client.get("/api/auth/me")
    user2_id = me_resp.json()["id"]

    # Owner grants user role
    acl_resp = await user1_client.post(f"/api/agents/{agent_id}/acl", json={
        "user_id": user2_id,
        "role": "user",
    })
    assert acl_resp.status_code == 201

    # Now user2 can access
    resp = await user2_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_non_owner_cannot_manage_acl(user2_client: AsyncClient, user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client, "no-manage", "public")

    # user2 has implicit 'user' role on public agent, but cannot manage ACL
    resp = await user2_client.post(f"/api/agents/{agent_id}/acl", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "role": "user",
    })
    assert resp.status_code == 403

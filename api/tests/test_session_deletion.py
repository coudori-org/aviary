"""Tests for session deletion with full resource cleanup and agent soft-delete behavior."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


async def _create_agent(client: AsyncClient, slug: str) -> str:
    resp = await client.post("/api/agents", json={
        "name": f"Agent {slug}",
        "slug": slug,
        "instruction": "Be helpful.",
        "model_config": {"backend": "dummy-backend", "model": "dummy-model"},
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_session(client: AsyncClient, agent_id: str) -> str:
    resp = await client.post(f"/api/agents/{agent_id}/sessions", json={})
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Session Deletion ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_session(user1_client: AsyncClient):
    """Deleting a session returns 204 and removes it from DB."""
    agent_id = await _create_agent(user1_client, "del-sess")
    session_id = await _create_session(user1_client, agent_id)

    with patch("app.services.agent_supervisor.cleanup_session", new_callable=AsyncMock):
        resp = await user1_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204

    # Session should be gone
    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_removes_messages(user1_client: AsyncClient):
    """Messages are cascade-deleted with the session."""
    agent_id = await _create_agent(user1_client, "del-msgs")
    session_id = await _create_session(user1_client, agent_id)

    # Verify session exists with empty messages
    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == []

    with patch("app.services.agent_supervisor.cleanup_session", new_callable=AsyncMock):
        resp = await user1_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204

    # Session gone — 404
    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_not_found(user1_client: AsyncClient):
    resp = await user1_client.delete("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_forbidden_for_non_creator(
    user1_client: AsyncClient, user3_client: AsyncClient,
):
    """Only session creator can delete."""
    agent_id = await _create_agent(user1_client, "del-perm")
    session_id = await _create_session(user1_client, agent_id)

    # user3 is not the creator
    resp = await user3_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_session_does_not_affect_other_sessions(user1_client: AsyncClient):
    """Deleting one session leaves other sessions intact."""
    agent_id = await _create_agent(user1_client, "del-other")
    session1 = await _create_session(user1_client, agent_id)
    session2 = await _create_session(user1_client, agent_id)

    with patch("app.services.agent_supervisor.cleanup_session", new_callable=AsyncMock):
        resp = await user1_client.delete(f"/api/sessions/{session1}")
    assert resp.status_code == 204

    # session2 still exists
    resp = await user1_client.get(f"/api/sessions/{session2}")
    assert resp.status_code == 200

    # session list should have 1
    resp = await user1_client.get(f"/api/agents/{agent_id}/sessions")
    assert len(resp.json()["items"]) == 1


# ── Session Title Update ──────────────────────────────────────


@pytest.mark.asyncio
async def test_update_session_title(user1_client: AsyncClient):
    agent_id = await _create_agent(user1_client, "title-edit")
    session_id = await _create_session(user1_client, agent_id)

    resp = await user1_client.patch(
        f"/api/sessions/{session_id}/title",
        json={"title": "My Custom Title"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My Custom Title"

    # Verify persisted
    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.json()["session"]["title"] == "My Custom Title"


# ── Agent Soft Delete ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_agent_with_sessions_keeps_sessions(user1_client: AsyncClient):
    """Deleting an agent with active sessions is a soft delete — sessions remain."""
    agent_id = await _create_agent(user1_client, "soft-del")
    session_id = await _create_session(user1_client, agent_id)

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    # Agent is still accessible via direct GET (include_deleted=True in router)
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Session still works
    resp = await user1_client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_deleted_agent_blocks_new_sessions(user1_client: AsyncClient):
    """Cannot create new sessions on a deleted agent (HTTP 410)."""
    agent_id = await _create_agent(user1_client, "no-new-sess")
    # Create a session first so the agent is soft-deleted (not hard-deleted)
    await _create_session(user1_client, agent_id)

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    resp = await user1_client.post(f"/api/agents/{agent_id}/sessions", json={})
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_deleted_agent_config_still_editable(user1_client: AsyncClient):
    """Config editing works on deleted agents."""
    agent_id = await _create_agent(user1_client, "edit-del")
    await _create_session(user1_client, agent_id)

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    resp = await user1_client.put(f"/api/agents/{agent_id}", json={
        "instruction": "Updated instruction after delete",
    })
    assert resp.status_code == 200
    assert resp.json()["instruction"] == "Updated instruction after delete"


@pytest.mark.asyncio
async def test_deleted_agent_visible_in_list_with_sessions(user1_client: AsyncClient):
    """Deleted agents with active sessions still appear in agent list."""
    agent_id = await _create_agent(user1_client, "visible-del")
    await _create_session(user1_client, agent_id)

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    resp = await user1_client.get("/api/agents")
    agent_ids = [a["id"] for a in resp.json()["items"]]
    assert agent_id in agent_ids


@pytest.mark.asyncio
async def test_deleted_agent_hard_deleted_after_all_sessions_removed(user1_client: AsyncClient):
    """Once all sessions of a deleted agent are removed, agent is hard-deleted."""
    agent_id = await _create_agent(user1_client, "hidden-del")
    session_id = await _create_session(user1_client, agent_id)

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    # Agent still exists (soft-deleted, has sessions)
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    with patch("app.services.agent_supervisor.cleanup_session", new_callable=AsyncMock):
        resp = await user1_client.delete(f"/api/sessions/{session_id}")
    assert resp.status_code == 204

    # Agent is now hard-deleted
    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_agent_without_sessions_is_hard_deleted(user1_client: AsyncClient):
    """Agent with no sessions is hard-deleted immediately."""
    agent_id = await _create_agent(user1_client, "imm-del")

    resp = await user1_client.delete(f"/api/agents/{agent_id}")
    assert resp.status_code == 204

    resp = await user1_client.get(f"/api/agents/{agent_id}")
    assert resp.status_code == 404

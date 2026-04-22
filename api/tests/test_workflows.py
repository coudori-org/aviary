from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

_MODEL_CONFIG = {"backend": "dummy-backend", "model": "dummy-model"}


async def _create(client: AsyncClient, slug: str) -> dict:
    resp = await client.post("/api/workflows", json={
        "name": f"Workflow {slug}",
        "slug": slug,
        "model_config": _MODEL_CONFIG,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_create_lists_with_current_version_null(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-fresh")
    assert wf["status"] == "draft"
    assert wf["current_version"] is None


@pytest.mark.asyncio
async def test_deploy_creates_version_and_flips_status(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-deploy")
    wf_id = wf["id"]

    resp = await user1_client.post(f"/api/workflows/{wf_id}/deploy")
    assert resp.status_code == 200, resp.text
    v1 = resp.json()
    assert v1["version"] == 1
    assert v1["workflow_id"] == wf_id

    resp = await user1_client.post(f"/api/workflows/{wf_id}/deploy")
    v2 = resp.json()
    assert v2["version"] == 2

    # Workflow now reports deployed + current_version = 2
    resp = await user1_client.get(f"/api/workflows/{wf_id}")
    data = resp.json()
    assert data["status"] == "deployed"
    assert data["current_version"] == 2

    # Versions listed newest-first
    resp = await user1_client.get(f"/api/workflows/{wf_id}/versions")
    versions = resp.json()
    assert [v["version"] for v in versions] == [2, 1]


@pytest.mark.asyncio
async def test_edit_flips_status_back_to_draft(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-edit")
    wf_id = wf["id"]
    await user1_client.post(f"/api/workflows/{wf_id}/deploy")

    resp = await user1_client.post(f"/api/workflows/{wf_id}/edit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "draft"
    # Edit must not erase version history
    assert data["current_version"] == 1


@pytest.mark.asyncio
async def test_non_owner_cannot_deploy_or_list_versions(
    user1_client: AsyncClient, user2_client: AsyncClient
):
    wf = await _create(user1_client, "wf-acl")
    wf_id = wf["id"]

    resp = await user2_client.post(f"/api/workflows/{wf_id}/deploy")
    assert resp.status_code == 403

    resp = await user2_client.get(f"/api/workflows/{wf_id}/versions")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_versions_empty_for_never_deployed(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-novers")
    wf_id = wf["id"]
    resp = await user1_client.get(f"/api/workflows/{wf_id}/versions")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Runs ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_draft_run_inserts_row_and_starts_workflow(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-draftrun")
    wf_id = wf["id"]

    resp = await user1_client.post(
        f"/api/workflows/{wf_id}/runs",
        json={"run_type": "draft", "trigger_type": "manual", "trigger_data": {"hello": "world"}},
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["run_type"] == "draft"
    assert run["trigger_type"] == "manual"
    assert run["trigger_data"] == {"hello": "world"}
    assert run["status"] == "pending"
    assert run["version_id"] is None


@pytest.mark.asyncio
async def test_trigger_deployed_run_without_version_returns_400(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-noverrun")
    wf_id = wf["id"]

    resp = await user1_client.post(
        f"/api/workflows/{wf_id}/runs",
        json={"run_type": "deployed"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_trigger_deployed_run_after_deploy(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-deprun")
    wf_id = wf["id"]
    await user1_client.post(f"/api/workflows/{wf_id}/deploy")

    resp = await user1_client.post(
        f"/api/workflows/{wf_id}/runs",
        json={"run_type": "deployed"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version_id"] is not None


@pytest.mark.asyncio
async def test_list_runs_excludes_drafts_by_default(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-listrun")
    wf_id = wf["id"]
    await user1_client.post(f"/api/workflows/{wf_id}/deploy")
    # one draft + one deployed
    await user1_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "draft"})
    await user1_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "deployed"})

    resp = await user1_client.get(f"/api/workflows/{wf_id}/runs")
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["run_type"] == "deployed"

    resp = await user1_client.get(f"/api/workflows/{wf_id}/runs?include_drafts=true")
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_cancel_run_returns_accepted(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-cancelrun")
    wf_id = wf["id"]
    r = await user1_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "draft"})
    run_id = r.json()["id"]

    resp = await user1_client.post(f"/api/workflows/{wf_id}/runs/{run_id}/cancel")
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_non_owner_cannot_trigger_run(
    user1_client: AsyncClient, user2_client: AsyncClient,
):
    wf = await _create(user1_client, "wf-runacl")
    wf_id = wf["id"]
    resp = await user2_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "draft"})
    assert resp.status_code == 403


# ── Delete ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_workflow_hard_deletes_with_no_runs(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-del-empty")
    wf_id = wf["id"]

    resp = await user1_client.delete(f"/api/workflows/{wf_id}")
    assert resp.status_code == 204

    resp = await user1_client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_workflow_cascades_runs_and_cleans_artifacts(user1_client: AsyncClient):
    """Workflow delete terminates in-flight Temporal runs, wipes artifact trees
    for every root_run_id, and cascades runs + node_runs out of the DB."""
    wf = await _create(user1_client, "wf-del-cascade")
    wf_id = wf["id"]
    await user1_client.post(f"/api/workflows/{wf_id}/deploy")

    r1 = await user1_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "draft"})
    r2 = await user1_client.post(f"/api/workflows/{wf_id}/runs", json={"run_type": "deployed"})
    run_ids = {r1.json()["id"], r2.json()["id"]}

    with (
        patch(
            "app.services.agent_supervisor.cleanup_workflow_artifacts",
            new_callable=AsyncMock,
        ) as artifacts,
        patch(
            "app.services.temporal_client.terminate_workflow_run",
            new_callable=AsyncMock, return_value=True,
        ) as terminate,
    ):
        resp = await user1_client.delete(f"/api/workflows/{wf_id}")
        assert resp.status_code == 204

        # Every in-flight (pending) run got a terminate call.
        terminated_ids = {call.args[0] for call in terminate.await_args_list}
        assert terminated_ids == run_ids

        # Each run's root — with root_run_id NULL, the run's own id is used.
        cleaned_roots = {call.args[0] for call in artifacts.await_args_list}
        assert cleaned_roots == run_ids

    # Workflow + runs both gone.
    resp = await user1_client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 404
    resp = await user1_client.get(f"/api/workflows/{wf_id}/runs?include_drafts=true")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_workflow_removes_from_list(user1_client: AsyncClient):
    wf = await _create(user1_client, "wf-del-list")
    wf_id = wf["id"]

    resp = await user1_client.delete(f"/api/workflows/{wf_id}")
    assert resp.status_code == 204

    resp = await user1_client.get("/api/workflows")
    ids = [w["id"] for w in resp.json()["items"]]
    assert wf_id not in ids


@pytest.mark.asyncio
async def test_non_owner_cannot_delete_workflow(
    user1_client: AsyncClient, user2_client: AsyncClient,
):
    wf = await _create(user1_client, "wf-del-acl")
    wf_id = wf["id"]

    resp = await user2_client.delete(f"/api/workflows/{wf_id}")
    assert resp.status_code == 403

    # Still there for the owner.
    resp = await user1_client.get(f"/api/workflows/{wf_id}")
    assert resp.status_code == 200

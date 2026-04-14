"""K3S backend — Protocol compliance and K8s call shape."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.backends.k3s.backend import K3SBackend
from app.backends.k3s.identity import K3SIdentityBinder
from app.backends.k3s.workspace import K3SWorkspaceStore
from app.backends.protocol import AgentSpec


def _spec(agent_id: str = "agent-test-1") -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id,
        owner_id="owner-1",
        image="aviary-runtime:latest",
        sa_name="agent-default-sa",
        min_pods=0,
        max_pods=3,
    )


@pytest.fixture
def k8s_apply():
    """Patch the single K8s API entry point used across K3S backend modules."""
    with patch("app.backends.k3s.workspace.k8s_apply", new_callable=AsyncMock) as w, \
         patch("app.backends.k3s.identity.k8s_apply", new_callable=AsyncMock) as i, \
         patch("app.backends.k3s.backend.k8s_apply", new_callable=AsyncMock) as b, \
         patch("app.backends.k3s.backend.apply_or_replace", new_callable=AsyncMock) as br, \
         patch("app.backends.k3s.identity.apply_or_replace", new_callable=AsyncMock) as ir, \
         patch("app.backends._common.k8s_client.k8s_apply", new_callable=AsyncMock) as c:
        yield {
            "workspace": w, "identity": i, "backend": b,
            "backend_replace": br, "identity_replace": ir, "common": c,
        }


@pytest.mark.asyncio
async def test_register_agent_creates_sa_pvc_deployment_service_and_scaledobject(k8s_apply):
    backend = K3SBackend()
    await backend.register_agent(_spec())

    # SA POST, PV POST, PVC POST — via identity/workspace k8s_apply
    assert k8s_apply["identity"].await_count >= 1
    assert k8s_apply["workspace"].await_count >= 2  # PV + PVC

    # Deployment + Service + ScaledObject via apply_or_replace
    assert k8s_apply["backend_replace"].await_count == 3


@pytest.mark.asyncio
async def test_unregister_deletes_all_resources(k8s_apply):
    backend = K3SBackend()
    await backend.unregister_agent("agent-test-1")

    # unbind_identity (NetworkPolicy DELETE) via identity module
    delete_calls = k8s_apply["identity"].await_args_list
    assert any(c.args[0] == "DELETE" for c in delete_calls)

    # Deployment + Service + ScaledObject DELETE via backend module
    backend_calls = k8s_apply["backend"].await_args_list
    assert len([c for c in backend_calls if c.args[0] == "DELETE"]) == 3

    # PVC + PV DELETE via workspace module
    workspace_calls = k8s_apply["workspace"].await_args_list
    assert len([c for c in workspace_calls if c.args[0] == "DELETE"]) == 2


@pytest.mark.asyncio
async def test_ensure_active_scales_when_idle(k8s_apply):
    """ensure_active patches replicas=1 when current is 0."""
    k8s_apply["backend"].return_value = {"spec": {"replicas": 0}, "status": {}}

    backend = K3SBackend()
    await backend.ensure_active("agent-test-1")

    # One GET (deployment lookup) + one PATCH (scale)
    methods = [c.args[0] for c in k8s_apply["backend"].await_args_list]
    assert "GET" in methods
    assert "PATCH" in methods


@pytest.mark.asyncio
async def test_ensure_active_noop_when_already_running(k8s_apply):
    k8s_apply["backend"].return_value = {"spec": {"replicas": 2}, "status": {}}
    backend = K3SBackend()
    await backend.ensure_active("agent-test-1")

    methods = [c.args[0] for c in k8s_apply["backend"].await_args_list]
    assert methods == ["GET"]


@pytest.mark.asyncio
async def test_get_status_returns_zero_on_404(k8s_apply):
    req = httpx.Request("GET", "http://k8s/test")
    k8s_apply["backend"].side_effect = httpx.HTTPStatusError(
        "Not Found", request=req, response=httpx.Response(404, request=req),
    )
    backend = K3SBackend()
    status = await backend.get_status("agent-test-1")
    assert status.exists is False
    assert status.replicas == 0


@pytest.mark.asyncio
async def test_get_status_reads_replica_counts(k8s_apply):
    k8s_apply["backend"].return_value = {
        "spec": {"replicas": 2},
        "status": {"replicas": 2, "readyReplicas": 1, "updatedReplicas": 2},
    }
    backend = K3SBackend()
    status = await backend.get_status("agent-test-1")
    assert status.exists
    assert status.ready_replicas == 1
    assert status.updated_replicas == 2


@pytest.mark.asyncio
async def test_bind_identity_single_profile(k8s_apply):
    k8s_apply["identity"].return_value = {
        "data": {"github.json": '[{"to": [{"ipBlock": {"cidr": "1.2.3.0/24"}}]}]'},
    }

    binder = K3SIdentityBinder()
    await binder.bind_identity("agent-test-1", "agent-default-sa", ["github"])

    k8s_apply["identity_replace"].assert_awaited_once()
    manifest = k8s_apply["identity_replace"].await_args.args[2]
    assert len(manifest["spec"]["egress"]) == 1
    assert manifest["spec"]["egress"][0]["to"][0]["ipBlock"]["cidr"] == "1.2.3.0/24"


@pytest.mark.asyncio
async def test_bind_identity_merges_multiple_profiles(k8s_apply):
    """AWS SG semantics: multiple sg_refs → union of all egress rules."""
    k8s_apply["identity"].return_value = {
        "data": {
            "default.json": '[{"to": [{"ipBlock": {"cidr": "10.0.0.0/8"}}]}]',
            "github.json": '[{"to": [{"ipBlock": {"cidr": "140.82.112.0/20"}}]}]',
        },
    }

    binder = K3SIdentityBinder()
    await binder.bind_identity("agent-test-1", "agent-default-sa", ["default", "github"])

    manifest = k8s_apply["identity_replace"].await_args.args[2]
    cidrs = [r["to"][0]["ipBlock"]["cidr"] for r in manifest["spec"]["egress"]]
    assert "10.0.0.0/8" in cidrs
    assert "140.82.112.0/20" in cidrs
    assert len(cidrs) == 2


@pytest.mark.asyncio
async def test_bind_identity_unknown_profile_raises_400(k8s_apply):
    from fastapi import HTTPException
    k8s_apply["identity"].return_value = {"data": {}}

    binder = K3SIdentityBinder()
    with pytest.raises(HTTPException) as exc:
        await binder.bind_identity("agent-test-1", "agent-default-sa", ["nonexistent"])
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_bind_identity_empty_refs_raises_400(k8s_apply):
    from fastapi import HTTPException
    binder = K3SIdentityBinder()
    with pytest.raises(HTTPException) as exc:
        await binder.bind_identity("agent-test-1", "agent-default-sa", [])
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_workspace_ref_returns_pvc_volume(k8s_apply):
    store = K3SWorkspaceStore()
    ref = await store.ensure_agent_workspace("agent-test-1")

    assert ref.volume["persistentVolumeClaim"]["claimName"].endswith("-workspace")
    assert ref.volume_mount["mountPath"] == "/workspace"


@pytest.mark.asyncio
async def test_resolve_endpoint_shape():
    backend = K3SBackend()
    ep = await backend.resolve_endpoint("agent-test-1")
    assert "/namespaces/agents/services/agent-agent-test-1-svc:3000/proxy" in ep


@pytest.mark.asyncio
async def test_scale_patches_replicas(k8s_apply):
    backend = K3SBackend()
    await backend.scale("agent-test-1", 3)
    call = k8s_apply["backend"].await_args
    assert call.args[0] == "PATCH"
    assert call.args[2] == {"spec": {"replicas": 3}}

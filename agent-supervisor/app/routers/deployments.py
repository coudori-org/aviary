"""Deployment lifecycle: Deployment + Service + PVC per agent."""

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.k8s import k8s_apply
from app.manifests import build_deployment_manifest, build_pvc_manifest, build_service_manifest

logger = logging.getLogger(__name__)

router = APIRouter()


class EnsureDeploymentRequest(BaseModel):
    agent_id: str
    owner_id: str
    policy: dict
    min_pods: int = 1
    max_pods: int = 3
    model_config_data: dict | None = None


@router.post("/deployments/{namespace}/ensure")
async def ensure_deployment(namespace: str, body: EnsureDeploymentRequest):
    """Create Deployment + Service + PVC if not exist. Returns namespace and whether created."""
    # Check if Deployment already exists
    try:
        result = await k8s_apply(
            "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime"
        )
        if result.get("metadata", {}).get("name") == "agent-runtime":
            # Deployment exists — but if scaled to zero, scale it back up
            replicas = result.get("spec", {}).get("replicas", 0)
            if replicas == 0:
                await k8s_apply(
                    "PATCH",
                    f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
                    {"spec": {"replicas": body.min_pods or 1}},
                )
                logger.info("Scaled up idle deployment in %s to %d", namespace, body.min_pods or 1)
            return {"namespace": namespace, "created": False}
    except httpx.HTTPError:
        pass

    # Ensure namespace exists (re-provision if lost)
    try:
        await k8s_apply("GET", f"/api/v1/namespaces/{namespace}")
    except httpx.HTTPError:
        logger.info("Namespace %s not found, re-provisioning", namespace)
        from app.routers.namespaces import CreateNamespaceRequest, create_namespace
        await create_namespace(CreateNamespaceRequest(
            agent_id=body.agent_id,
            owner_id=body.owner_id,
            policy=body.policy,
        ))

    # Create PVC
    await _create_pvc(namespace, body.agent_id)
    # Create Deployment
    await _create_deployment(namespace, body)
    # Create Service
    await _create_service(namespace)

    logger.info("Created Deployment for agent %s in namespace %s", body.agent_id, namespace)
    return {"namespace": namespace, "created": True}


@router.get("/deployments/{namespace}/status")
async def get_deployment_status(namespace: str):
    """Get Deployment status including replica counts."""
    try:
        result = await k8s_apply(
            "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime"
        )
        status = result.get("status", {})
        return {
            "replicas": status.get("replicas", 0),
            "ready_replicas": status.get("readyReplicas", 0),
            "updated_replicas": status.get("updatedReplicas", 0),
        }
    except httpx.HTTPError:  # Best-effort: deployment may not exist
        return {"replicas": 0, "ready_replicas": 0, "updated_replicas": 0}


@router.get("/deployments/{namespace}/ready")
async def wait_for_ready(namespace: str, timeout: int = Query(default=90)):
    """Long-poll until Deployment has at least 1 ready replica or timeout."""
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            result = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime"
            )
            status = result.get("status", {})
            ready_replicas = status.get("readyReplicas", 0)
            if ready_replicas and ready_replicas >= 1:
                return {"ready": True}

            conditions = status.get("conditions", [])
            for cond in conditions:
                if cond.get("type") == "Available" and cond.get("status") == "True":
                    return {"ready": True}
        except httpx.HTTPError:  # Best-effort: poll until ready or timeout
            pass

        await asyncio.sleep(2)

    return {"ready": False}


class ScaleRequest(BaseModel):
    replicas: int
    min_pods: int = 1
    max_pods: int = 3


@router.patch("/deployments/{namespace}/scale")
async def scale_deployment(namespace: str, body: ScaleRequest):
    """Scale the agent Deployment to the specified replica count."""
    replicas = max(body.min_pods, min(body.replicas, body.max_pods))
    await k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
        {"spec": {"replicas": replicas}},
    )
    logger.info("Scaled deployment in %s to %d replicas", namespace, replicas)
    return {"ok": True, "replicas": replicas}


@router.patch("/deployments/{namespace}/scale-to-zero")
async def scale_to_zero(namespace: str):
    """Scale agent Deployment to 0 (idle timeout)."""
    try:
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
            {"spec": {"replicas": 0}},
        )
    except httpx.HTTPError:
        logger.warning("Failed to scale down deployment in %s", namespace, exc_info=True)
    return {"ok": True}


@router.delete("/deployments/{namespace}")
async def delete_deployment(namespace: str):
    """Delete the Deployment, Service, and PVC for an agent."""
    for path in [
        f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
        f"/api/v1/namespaces/{namespace}/services/agent-runtime-svc",
        f"/api/v1/namespaces/{namespace}/persistentvolumeclaims/agent-workspace",
    ]:
        try:
            await k8s_apply("DELETE", path)
        except httpx.HTTPError:  # Best-effort: resource may already be gone
            logger.warning("Failed to delete %s", path, exc_info=True)
    logger.info("Deleted deployment resources in namespace %s", namespace)
    return {"ok": True}


@router.post("/deployments/{namespace}/restart")
async def rolling_restart(namespace: str):
    """Trigger a rolling restart of the agent Deployment."""
    await k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
        {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "aviary/restartedAt": str(int(time.time())),
                        }
                    }
                }
            }
        },
    )
    logger.info("Triggered rolling restart in namespace %s", namespace)
    return {"ok": True}


@router.delete("/deployments/{namespace}/sessions/{session_id}")
async def cleanup_session_workspace(namespace: str, session_id: str):
    """Delete a session's workspace directory on the PVC via the runtime Pod."""
    proxy_path = (
        f"/api/v1/namespaces/{namespace}/services/"
        f"agent-runtime-svc:3000/proxy/sessions/{session_id}/workspace"
    )
    try:
        result = await k8s_apply("DELETE", proxy_path)
        return result
    except httpx.HTTPError:
        # Best-effort: Pod may be scaled to zero or not running — workspace will be cleaned
        # up when the PVC is eventually deleted (agent K8s teardown).
        logger.info(
            "Session workspace cleanup skipped for %s in %s (pod not reachable)",
            session_id, namespace,
        )
        return {"status": "skipped", "reason": "pod_not_reachable"}


@router.get("/pods/{namespace}/metrics")
async def get_pod_metrics(namespace: str):
    """Query metrics from all running pods in the namespace."""
    total_active = 0
    total_streaming = 0
    pods_queried = 0

    try:
        pod_list = await k8s_apply(
            "GET",
            f"/api/v1/namespaces/{namespace}/pods?labelSelector=aviary/role=agent-runtime",
        )
        pods = pod_list.get("items", [])

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name")
            phase = pod.get("status", {}).get("phase")
            if not pod_name or phase != "Running":
                continue

            try:
                metrics = await k8s_apply(
                    "GET",
                    f"/api/v1/namespaces/{namespace}/pods/{pod_name}:3000/proxy/metrics",
                )
                total_active += metrics.get("sessions_active", 0)
                total_streaming += metrics.get("sessions_streaming", 0)
                pods_queried += 1
            except httpx.HTTPError:  # Best-effort: individual pod metrics may be unavailable
                pass
    except httpx.HTTPError:  # Best-effort: pod listing may fail
        pass

    return {
        "total_active": total_active,
        "total_streaming": total_streaming,
        "pods_queried": pods_queried,
    }


# ── Internal helpers ──────────────────────────────────────────


async def _create_pvc(namespace: str, agent_id: str) -> None:
    await k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/persistentvolumeclaims",
        build_pvc_manifest(namespace, agent_id),
    )


async def _create_deployment(namespace: str, body: EnsureDeploymentRequest) -> None:
    await k8s_apply(
        "POST",
        f"/apis/apps/v1/namespaces/{namespace}/deployments",
        build_deployment_manifest(
            namespace=namespace,
            agent_id=body.agent_id,
            min_pods=body.min_pods,
            policy=body.policy or {},
        ),
    )


async def _create_service(namespace: str) -> None:
    await k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/services",
        build_service_manifest(namespace),
    )

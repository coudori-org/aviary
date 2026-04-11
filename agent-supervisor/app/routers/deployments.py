"""K8s-specific deployment endpoints used by the admin console."""

import logging
import time

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from aviary_shared.naming import DEPLOYMENT_NAME, RUNTIME_PORT, runtime_label_selector

from app.k8s import k8s_apply
from app import provisioning

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
    """Create Deployment + Service + PVC if not exist."""
    return await provisioning.ensure_deployment(
        namespace=namespace,
        agent_id=body.agent_id,
        owner_id=body.owner_id,
        policy=body.policy or {},
        min_pods=body.min_pods,
        max_pods=body.max_pods,
    )


@router.get("/deployments/{namespace}/status")
async def get_deployment_status(namespace: str):
    """Get Deployment status. Raises 404 if the Deployment does not exist
    so callers can distinguish "scaled to zero" from "never deployed"."""
    return await provisioning.get_deployment_status(namespace)


@router.get("/deployments/{namespace}/ready")
async def wait_for_ready(namespace: str, timeout: int = Query(default=90)):
    """Long-poll until Deployment has at least 1 ready replica or timeout."""
    return await provisioning.wait_for_ready(namespace, timeout)


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
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}",
        {"spec": {"replicas": replicas}},
    )
    logger.info("Scaled deployment in %s to %d replicas", namespace, replicas)
    return {"ok": True, "replicas": replicas}


@router.patch("/deployments/{namespace}/scale-to-zero")
async def scale_to_zero(namespace: str):
    """Scale agent Deployment to 0 (idle timeout)."""
    await k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}",
        {"spec": {"replicas": 0}},
    )
    return {"ok": True}


@router.delete("/deployments/{namespace}")
async def delete_deployment(namespace: str):
    """Permanently delete all per-agent resources (Deployment, Service,
    PVC, and the cluster-scoped PV). Called when an agent is being
    fully removed along with all of its sessions."""
    from aviary_shared.naming import (
        PVC_NAME, SERVICE_NAME, agent_id_from_namespace, agent_pv_name,
    )
    agent_id = agent_id_from_namespace(namespace)
    for path in [
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}",
        f"/api/v1/namespaces/{namespace}/services/{SERVICE_NAME}",
        f"/api/v1/namespaces/{namespace}/persistentvolumeclaims/{PVC_NAME}",
        f"/api/v1/persistentvolumes/{agent_pv_name(agent_id)}",
    ]:
        await k8s_apply("DELETE", path)
    logger.info("Deleted deployment resources in namespace %s", namespace)
    return {"ok": True}


@router.post("/deployments/{namespace}/restart")
async def rolling_restart(namespace: str):
    """Trigger a rolling restart of the agent Deployment."""
    await k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}",
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
    return await provisioning.cleanup_session_workspace(namespace, session_id)


@router.get("/pods/{namespace}/metrics")
async def get_pod_metrics(namespace: str):
    """Query metrics from all running pods in the namespace."""
    total_active = 0
    total_streaming = 0
    pods_queried = 0

    try:
        pod_list = await k8s_apply(
            "GET",
            f"/api/v1/namespaces/{namespace}/pods?labelSelector={runtime_label_selector()}",
        )
    except httpx.HTTPError:
        logger.warning("Pod list query failed for namespace %s", namespace, exc_info=True)
        return {"total_active": 0, "total_streaming": 0, "pods_queried": 0}

    for pod in pod_list.get("items", []):
        pod_name = pod.get("metadata", {}).get("name")
        phase = pod.get("status", {}).get("phase")
        if not pod_name or phase != "Running":
            continue
        try:
            metrics = await k8s_apply(
                "GET",
                f"/api/v1/namespaces/{namespace}/pods/{pod_name}:{RUNTIME_PORT}/proxy/metrics",
            )
            total_active += metrics.get("sessions_active", 0)
            total_streaming += metrics.get("sessions_streaming", 0)
            pods_queried += 1
        except httpx.HTTPError:
            logger.warning("Metrics fetch failed for pod %s", pod_name, exc_info=True)

    return {
        "total_active": total_active,
        "total_streaming": total_streaming,
        "pods_queried": pods_queried,
    }

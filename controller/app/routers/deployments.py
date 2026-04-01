"""Deployment lifecycle: Deployment + Service + PVC per agent."""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.k8s import k8s_apply

logger = logging.getLogger(__name__)

router = APIRouter()

# Platform service URLs (used in Pod env vars)
_EGRESS_PROXY_URL = "http://egress-proxy.platform.svc:8080"
_NO_PROXY = (
    "credential-proxy.platform.svc,"
    "inference-router.platform.svc,"
    "egress-proxy.platform.svc,"
    ".svc,.svc.cluster.local,"
    "localhost,127.0.0.1"
)
_NODE_OPTIONS = "--require /app/scripts/proxy-bootstrap.js"


class EnsureDeploymentRequest(BaseModel):
    agent_id: str
    owner_id: str
    instruction: str
    tools: list
    policy: dict
    mcp_servers: list
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
            return {"namespace": namespace, "created": False}
    except Exception:
        pass

    # Ensure namespace exists (re-provision if lost)
    try:
        await k8s_apply("GET", f"/api/v1/namespaces/{namespace}")
    except Exception:
        logger.info("Namespace %s not found, re-provisioning", namespace)
        from app.routers.namespaces import CreateNamespaceRequest, create_namespace
        await create_namespace(CreateNamespaceRequest(
            agent_id=body.agent_id,
            owner_id=body.owner_id,
            instruction=body.instruction,
            tools=body.tools,
            policy=body.policy,
            mcp_servers=body.mcp_servers,
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
    except Exception:
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
        except Exception:
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
    except Exception:
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
        except Exception:
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
            except Exception:
                pass
    except Exception:
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
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "agent-workspace",
                "namespace": namespace,
                "labels": {"aviary/agent-id": agent_id},
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "5Gi"}},
                "storageClassName": "local-path",
            },
        },
    )


async def _create_deployment(namespace: str, body: EnsureDeploymentRequest) -> None:
    policy = body.policy or {}
    memory_limit = policy.get("maxMemoryPerSession", "4Gi")
    cpu_limit = policy.get("maxCpuPerSession", "4")
    container_image = policy.get("containerImage", settings.agent_runtime_image)
    max_sessions = policy.get(
        "maxConcurrentSessionsPerPod", settings.max_concurrent_sessions_per_pod
    )

    await k8s_apply(
        "POST",
        f"/apis/apps/v1/namespaces/{namespace}/deployments",
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "agent-runtime",
                "namespace": namespace,
                "labels": {
                    "aviary/agent-id": body.agent_id,
                    "aviary/role": "agent-runtime",
                },
            },
            "spec": {
                "replicas": body.min_pods,
                "selector": {"matchLabels": {"aviary/role": "agent-runtime"}},
                "template": {
                    "metadata": {
                        "labels": {
                            "aviary/role": "agent-runtime",
                            "aviary/agent-id": body.agent_id,
                        },
                    },
                    "spec": {
                        "serviceAccountName": "session-runner",
                        "securityContext": {
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "fsGroup": 1000,
                        },
                        "hostAliases": [
                            {
                                "ip": settings.host_gateway_ip,
                                "hostnames": ["host.k8s.internal"],
                            }
                        ],
                        "containers": [
                            {
                                "name": "agent-runtime",
                                "image": container_image,
                                "imagePullPolicy": "Never",
                                "ports": [{"containerPort": 3000}],
                                "env": [
                                    {"name": "AGENT_ID", "value": body.agent_id},
                                    {"name": "MAX_CONCURRENT_SESSIONS", "value": str(max_sessions)},
                                    {"name": "CREDENTIAL_PROXY_URL", "value": "http://credential-proxy.platform.svc:8080"},
                                    {"name": "INFERENCE_ROUTER_URL", "value": "http://inference-router.platform.svc:8080"},
                                    {"name": "HOME", "value": "/tmp"},
                                    {"name": "HTTP_PROXY", "value": _EGRESS_PROXY_URL},
                                    {"name": "HTTPS_PROXY", "value": _EGRESS_PROXY_URL},
                                    {"name": "NO_PROXY", "value": _NO_PROXY},
                                    {"name": "NODE_OPTIONS", "value": _NODE_OPTIONS},
                                ],
                                "volumeMounts": [
                                    {"name": "agent-workspace", "mountPath": "/workspace"},
                                    {"name": "agent-config", "mountPath": "/agent/config", "readOnly": True},
                                ],
                                "resources": {
                                    "requests": {"cpu": "1", "memory": "1Gi"},
                                    "limits": {"cpu": cpu_limit, "memory": memory_limit},
                                },
                                "livenessProbe": {
                                    "httpGet": {"path": "/health", "port": 3000},
                                    "initialDelaySeconds": 5,
                                    "periodSeconds": 30,
                                },
                                "readinessProbe": {
                                    "httpGet": {"path": "/ready", "port": 3000},
                                    "initialDelaySeconds": 3,
                                },
                            }
                        ],
                        "volumes": [
                            {
                                "name": "agent-workspace",
                                "persistentVolumeClaim": {"claimName": "agent-workspace"},
                            },
                            {
                                "name": "agent-config",
                                "configMap": {"name": "agent-config"},
                            },
                        ],
                    },
                },
            },
        },
    )


async def _create_service(namespace: str) -> None:
    await k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/services",
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "agent-runtime-svc", "namespace": namespace},
            "spec": {
                "selector": {"aviary/role": "agent-runtime"},
                "ports": [{"port": 3000, "targetPort": 3000, "protocol": "TCP"}],
            },
        },
    )

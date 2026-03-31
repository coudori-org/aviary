"""Agent Deployment lifecycle management.

Manages K8s Deployment + Service + PVC per agent for the agent-per-pod architecture.
Replaces the old per-session Pod spawning logic.
"""

import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Agent
from app.services import k8s_service

logger = logging.getLogger(__name__)

# Platform service URLs
# Credential proxy and inference router run outside K8s (docker compose),
# reachable from pods via host gateway. Egress proxy stays in K8s.
_EGRESS_PROXY_URL = "http://egress-proxy.platform.svc:8080"
_NO_PROXY = (
    "credential-proxy.platform.svc,"
    "inference-router.platform.svc,"
    "egress-proxy.platform.svc,"
    ".svc,.svc.cluster.local,"
    "localhost,127.0.0.1"
)
_NODE_OPTIONS = "--require /app/scripts/proxy-bootstrap.js"


@lru_cache(maxsize=1)
def _get_host_gateway_ip() -> str:
    """Get the Docker/K8s host gateway IP for Pod -> host communication."""
    gateway = os.environ.get("K8S_GATEWAY_IP")
    if not gateway:
        raise RuntimeError("K8S_GATEWAY_IP environment variable is required")
    return gateway


def _service_proxy_path(namespace: str) -> str:
    """Return the K8s API proxy path to the agent's Service."""
    return f"/api/v1/namespaces/{namespace}/services/agent-runtime-svc:3000/proxy"


async def ensure_agent_deployment(db: AsyncSession, agent: Agent) -> str:
    """Ensure a Deployment + Service is running for the agent.

    Creates PVC, Deployment, and Service if they don't exist.
    Returns the agent namespace for routing.

    Respects pod_strategy:
    - "lazy": creates on first call (default behavior)
    - "eager": should be called at agent creation time
    - "manual": caller must check strategy before calling
    """
    if not agent.namespace:
        raise RuntimeError(f"Agent {agent.id} has no K8s namespace")

    namespace = agent.namespace

    # Check if Deployment already exists
    if agent.deployment_active:
        try:
            result = await k8s_service._k8s_apply(
                "GET",
                f"/apis/apps/v1/namespaces/{namespace}/deployments/agent-runtime",
            )
            if result.get("metadata", {}).get("name") == "agent-runtime":
                # Deployment exists, update activity timestamp
                agent.last_activity_at = datetime.now(timezone.utc)
                await db.flush()
                return namespace
        except Exception:
            # Deployment gone but DB says active — recreate
            logger.warning("Deployment not found for agent %s despite deployment_active=True, recreating", agent.id)

    # Ensure namespace exists (may have been lost on K8s reset)
    await _ensure_namespace(namespace, agent)

    # Create resources (idempotent — 409 Conflict is handled gracefully)
    await _create_agent_pvc(namespace, agent)
    await _create_agent_deployment(namespace, agent)
    await _create_agent_service(namespace)

    agent.deployment_active = True
    agent.last_activity_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info("Created Deployment for agent %s in namespace %s", agent.id, namespace)
    return namespace


async def _ensure_namespace(namespace: str, agent: Agent) -> None:
    """Ensure the agent namespace and its base resources exist.

    After a K8s reset, the namespace may be gone while the DB still references it.
    Re-provisions Namespace + NetworkPolicy + ResourceQuota + ServiceAccount.
    Uses POST which returns 409 if already exists (handled by _k8s_apply).
    """
    try:
        await k8s_service._k8s_apply("GET", f"/api/v1/namespaces/{namespace}")
        return  # namespace exists
    except Exception:
        logger.info("Namespace %s not found, re-provisioning K8s resources for agent %s", namespace, agent.id)

    await k8s_service.create_agent_namespace(
        agent_id=str(agent.id),
        owner_id=str(agent.owner_id),
        instruction=agent.instruction,
        tools=agent.tools,
        policy=agent.policy or {},
        mcp_servers=agent.mcp_servers or [],
    )


async def _create_agent_pvc(namespace: str, agent: Agent) -> None:
    """Create a shared PVC for all sessions of this agent."""
    await k8s_service._k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/persistentvolumeclaims",
        {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": "agent-workspace",
                "namespace": namespace,
                "labels": {"aviary/agent-id": str(agent.id)},
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "5Gi"}},
                "storageClassName": "local-path",
            },
        },
    )


async def _create_agent_deployment(namespace: str, agent: Agent) -> None:
    """Create a Deployment for the agent runtime."""
    policy = agent.policy or {}
    memory_limit = policy.get("maxMemoryPerSession", "512Mi")
    cpu_limit = policy.get("maxCpuPerSession", "500m")
    container_image = policy.get("containerImage", settings.agent_runtime_image)
    max_sessions_per_pod = policy.get("maxConcurrentSessionsPerPod", settings.max_concurrent_sessions_per_pod)
    replicas = agent.min_pods

    await k8s_service._k8s_apply(
        "POST",
        f"/apis/apps/v1/namespaces/{namespace}/deployments",
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "agent-runtime",
                "namespace": namespace,
                "labels": {
                    "aviary/agent-id": str(agent.id),
                    "aviary/role": "agent-runtime",
                },
            },
            "spec": {
                "replicas": replicas,
                "selector": {
                    "matchLabels": {"aviary/role": "agent-runtime"},
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "aviary/role": "agent-runtime",
                            "aviary/agent-id": str(agent.id),
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
                                "ip": _get_host_gateway_ip(),
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
                                    {"name": "AGENT_ID", "value": str(agent.id)},
                                    {"name": "MAX_CONCURRENT_SESSIONS", "value": str(max_sessions_per_pod)},
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
                                    "requests": {"cpu": "500m", "memory": "512Mi"},
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


async def _create_agent_service(namespace: str) -> None:
    """Create a Service to load-balance across agent runtime Pods."""
    await k8s_service._k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/services",
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "agent-runtime-svc",
                "namespace": namespace,
            },
            "spec": {
                "selector": {"aviary/role": "agent-runtime"},
                "ports": [{"port": 3000, "targetPort": 3000, "protocol": "TCP"}],
            },
        },
    )


async def scale_agent_deployment(agent: Agent, replicas: int) -> None:
    """Scale the agent Deployment to the specified replica count."""
    if not agent.namespace:
        return
    replicas = max(agent.min_pods, min(replicas, agent.max_pods))
    await k8s_service._k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{agent.namespace}/deployments/agent-runtime",
        {"spec": {"replicas": replicas}},
    )
    logger.info("Scaled agent %s deployment to %d replicas", agent.id, replicas)


async def scale_to_zero(db: AsyncSession, agent: Agent) -> None:
    """Scale agent Deployment to 0 (idle timeout)."""
    if not agent.namespace:
        return
    try:
        await k8s_service._k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{agent.namespace}/deployments/agent-runtime",
            {"spec": {"replicas": 0}},
        )
    except Exception:
        logger.warning("Failed to scale down agent %s", agent.id, exc_info=True)
    agent.deployment_active = False
    await db.flush()
    logger.info("Scaled agent %s deployment to 0 (idle)", agent.id)


async def delete_agent_deployment(agent: Agent) -> None:
    """Delete the Deployment, Service, and PVC for an agent."""
    if not agent.namespace:
        return
    ns = agent.namespace
    # Delete in order: Deployment, Service, PVC
    for path in [
        f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime",
        f"/api/v1/namespaces/{ns}/services/agent-runtime-svc",
        f"/api/v1/namespaces/{ns}/persistentvolumeclaims/agent-workspace",
    ]:
        try:
            await k8s_service._k8s_apply("DELETE", path)
        except Exception:
            logger.warning("Failed to delete %s", path, exc_info=True)
    logger.info("Deleted deployment resources for agent %s", agent.id)


async def get_deployment_status(agent: Agent) -> dict:
    """Get Deployment status including replica counts and pod names."""
    if not agent.namespace:
        return {"replicas": 0, "ready_replicas": 0, "pods": []}

    try:
        result = await k8s_service._k8s_apply(
            "GET",
            f"/apis/apps/v1/namespaces/{agent.namespace}/deployments/agent-runtime",
        )
        status = result.get("status", {})
        return {
            "replicas": status.get("replicas", 0),
            "ready_replicas": status.get("readyReplicas", 0),
            "updated_replicas": status.get("updatedReplicas", 0),
        }
    except Exception:
        return {"replicas": 0, "ready_replicas": 0, "pods": []}


async def rolling_restart(agent: Agent) -> None:
    """Trigger a rolling restart of the agent Deployment."""
    if not agent.namespace:
        return
    import time

    await k8s_service._k8s_apply(
        "PATCH",
        f"/apis/apps/v1/namespaces/{agent.namespace}/deployments/agent-runtime",
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
    logger.info("Triggered rolling restart for agent %s", agent.id)

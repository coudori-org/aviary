"""K8s resource manifest builders for agent deployments."""

from aviary_shared.naming import (
    DEPLOYMENT_NAME,
    LABEL_AGENT_ID,
    LABEL_ROLE,
    PVC_NAME,
    PVC_SIZE,
    RUNTIME_PORT,
    SERVICE_ACCOUNT_NAME,
    SERVICE_NAME,
    agent_pv_host_path,
    agent_pv_name,
)

from app.config import settings

_NODE_OPTIONS = "--require /app/scripts/proxy-bootstrap.js"


def build_pv_manifest(agent_id: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "name": agent_pv_name(agent_id),
            "labels": {LABEL_AGENT_ID: agent_id},
        },
        "spec": {
            "capacity": {"storage": PVC_SIZE},
            "accessModes": ["ReadWriteOnce"],
            "persistentVolumeReclaimPolicy": "Retain",
            "storageClassName": "",
            "hostPath": {
                "path": agent_pv_host_path(agent_id),
                "type": "DirectoryOrCreate",
            },
            "claimRef": {
                "namespace": f"agent-{agent_id}",
                "name": PVC_NAME,
            },
        },
    }


def build_pvc_manifest(namespace: str, agent_id: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": PVC_NAME,
            "namespace": namespace,
            "labels": {LABEL_AGENT_ID: agent_id},
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": PVC_SIZE}},
            "storageClassName": "",
            "volumeName": agent_pv_name(agent_id),
        },
    }


def build_deployment_manifest(
    namespace: str,
    agent_id: str,
    min_pods: int,
    policy: dict,
) -> dict:
    memory_limit = policy.get("maxMemoryPerSession", settings.default_memory_limit)
    cpu_limit = policy.get("maxCpuPerSession", settings.default_cpu_limit)
    container_image = policy.get("containerImage", settings.agent_runtime_image)
    max_sessions = policy.get(
        "maxConcurrentSessionsPerPod", settings.max_concurrent_sessions_per_pod
    )

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": DEPLOYMENT_NAME,
            "namespace": namespace,
            "labels": {
                LABEL_AGENT_ID: agent_id,
                LABEL_ROLE: DEPLOYMENT_NAME,
            },
        },
        "spec": {
            "replicas": min_pods,
            "selector": {"matchLabels": {LABEL_ROLE: DEPLOYMENT_NAME}},
            "template": {
                "metadata": {
                    "labels": {
                        LABEL_ROLE: DEPLOYMENT_NAME,
                        LABEL_AGENT_ID: agent_id,
                    },
                },
                "spec": {
                    "serviceAccountName": SERVICE_ACCOUNT_NAME,
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
                    # hostPath PVs aren't chowned by K8s the way local-path
                    # provisioner volumes are, so chown the workspace once
                    # at pod start. Idempotent.
                    "initContainers": [
                        {
                            "name": "fix-workspace-perms",
                            "image": container_image,
                            "imagePullPolicy": "Never",
                            "securityContext": {"runAsUser": 0, "runAsGroup": 0},
                            "command": ["chown", "-R", "1000:1000", "/workspace"],
                            "volumeMounts": [
                                {"name": PVC_NAME, "mountPath": "/workspace"},
                            ],
                            "resources": {
                                "requests": {"cpu": "10m", "memory": "16Mi"},
                                "limits": {"cpu": "100m", "memory": "64Mi"},
                            },
                        }
                    ],
                    "containers": [
                        {
                            "name": DEPLOYMENT_NAME,
                            "image": container_image,
                            "imagePullPolicy": "Never",
                            "ports": [{"containerPort": RUNTIME_PORT}],
                            "env": [
                                {"name": "AGENT_ID", "value": agent_id},
                                {"name": "MAX_CONCURRENT_SESSIONS", "value": str(max_sessions)},
                                {"name": "INFERENCE_ROUTER_URL", "value": settings.inference_router_url},
                                {"name": "MCP_GATEWAY_URL", "value": settings.mcp_gateway_url},
                                {"name": "LITELLM_API_KEY", "value": settings.litellm_api_key},
                                {"name": "HOME", "value": "/tmp"},
                                {"name": "HTTP_PROXY", "value": settings.egress_proxy_url},
                                {"name": "HTTPS_PROXY", "value": settings.egress_proxy_url},
                                {"name": "NO_PROXY", "value": settings.no_proxy},
                                {"name": "NODE_OPTIONS", "value": _NODE_OPTIONS},
                                {"name": "AVIARY_API_URL", "value": settings.aviary_api_url},
                                {"name": "AVIARY_INTERNAL_API_KEY", "value": settings.internal_api_key},
                            ],
                            "volumeMounts": [
                                {"name": PVC_NAME, "mountPath": "/workspace"},
                                {"name": "shared-workspace", "mountPath": "/workspace-shared"},
                            ],
                            "resources": {
                                "requests": {"cpu": "1", "memory": "1Gi"},
                                "limits": {"cpu": cpu_limit, "memory": memory_limit},
                            },
                            "livenessProbe": {
                                "httpGet": {"path": "/health", "port": RUNTIME_PORT},
                                "initialDelaySeconds": 5,
                                "periodSeconds": 30,
                            },
                            "readinessProbe": {
                                "httpGet": {"path": "/ready", "port": RUNTIME_PORT},
                                "initialDelaySeconds": 3,
                            },
                        }
                    ],
                    "volumes": [
                        {
                            "name": PVC_NAME,
                            "persistentVolumeClaim": {"claimName": PVC_NAME},
                        },
                        {
                            "name": "shared-workspace",
                            "hostPath": {"path": "/workspace-shared", "type": "DirectoryOrCreate"},
                        },
                    ],
                },
            },
        },
    }


def build_service_manifest(namespace: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": SERVICE_NAME, "namespace": namespace},
        "spec": {
            "selector": {LABEL_ROLE: DEPLOYMENT_NAME},
            "ports": [{"port": RUNTIME_PORT, "targetPort": RUNTIME_PORT, "protocol": "TCP"}],
        },
    }

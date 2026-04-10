"""K8s resource manifest builders for agent deployments."""

from app.config import settings

_NODE_OPTIONS = "--require /app/scripts/proxy-bootstrap.js"


def build_pvc_manifest(namespace: str, agent_id: str) -> dict:
    return {
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
    }


def build_deployment_manifest(
    namespace: str,
    agent_id: str,
    min_pods: int,
    policy: dict,
) -> dict:
    memory_limit = policy.get("maxMemoryPerSession", "4Gi")
    cpu_limit = policy.get("maxCpuPerSession", "4")
    container_image = policy.get("containerImage", settings.agent_runtime_image)
    max_sessions = policy.get(
        "maxConcurrentSessionsPerPod", settings.max_concurrent_sessions_per_pod
    )

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": "agent-runtime",
            "namespace": namespace,
            "labels": {
                "aviary/agent-id": agent_id,
                "aviary/role": "agent-runtime",
            },
        },
        "spec": {
            "replicas": min_pods,
            "selector": {"matchLabels": {"aviary/role": "agent-runtime"}},
            "template": {
                "metadata": {
                    "labels": {
                        "aviary/role": "agent-runtime",
                        "aviary/agent-id": agent_id,
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
                                {"name": "agent-workspace", "mountPath": "/workspace"},
                                {"name": "shared-workspace", "mountPath": "/workspace-shared"},
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
        "metadata": {"name": "agent-runtime-svc", "namespace": namespace},
        "spec": {
            "selector": {"aviary/role": "agent-runtime"},
            "ports": [{"port": 3000, "targetPort": 3000, "protocol": "TCP"}],
        },
    }

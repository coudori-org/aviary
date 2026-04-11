"""Centralized naming conventions for Aviary resources."""

# K8s resource names — used by agent-supervisor and admin console
DEPLOYMENT_NAME = "agent-runtime"
SERVICE_NAME = "agent-runtime-svc"
PVC_NAME = "agent-workspace"
PVC_SIZE = "5Gi"
PVC_STORAGE_CLASS = "local-path"
RUNTIME_PORT = 3000
NETWORK_POLICY_NAME = "session-egress"
RESOURCE_QUOTA_NAME = "session-quota"
SERVICE_ACCOUNT_NAME = "session-runner"
PLATFORM_NAMESPACE = "platform"
NETWORK_POLICY_BASE_CONFIGMAP = "network-policy-base"

# K8s labels
LABEL_ROLE = "aviary/role"
LABEL_AGENT_ID = "aviary/agent-id"
LABEL_OWNER = "aviary/owner"
LABEL_MANAGED = "aviary/managed"


def agent_namespace(agent_id: str | object) -> str:
    return f"agent-{agent_id}"


def runtime_label_selector() -> str:
    return f"{LABEL_ROLE}={DEPLOYMENT_NAME}"

"""Centralized naming conventions for Aviary resources."""

# K8s resource names — used by agent-supervisor and admin console
DEPLOYMENT_NAME = "agent-runtime"
SERVICE_NAME = "agent-runtime-svc"
PVC_NAME = "agent-workspace"
RUNTIME_PORT = 3000

# K8s labels
LABEL_ROLE = "aviary/role"
LABEL_AGENT_ID = "aviary/agent-id"


def agent_namespace(agent_id: str | object) -> str:
    """Derive K8s namespace name from agent ID."""
    return f"agent-{agent_id}"

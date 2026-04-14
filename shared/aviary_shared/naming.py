"""Centralized naming conventions for Aviary resources."""

PLATFORM_NAMESPACE = "platform"
AGENTS_NAMESPACE = "agents"

RUNTIME_PORT = 3000
PVC_SIZE = "5Gi"

PV_HOST_ROOT = "/var/lib/aviary/agent-workspace"

LABEL_ROLE = "aviary/role"
LABEL_AGENT_ID = "aviary/agent-id"
LABEL_OWNER = "aviary/owner"
LABEL_MANAGED = "aviary/managed"
LABEL_SG_REF = "aviary/sg-ref"

ROLE_RUNTIME = "agent-runtime"

DEFAULT_SA_NAME = "agent-default-sa"


def agent_deployment_name(agent_id: str) -> str:
    return f"agent-{agent_id}"


def agent_service_name(agent_id: str) -> str:
    return f"agent-{agent_id}-svc"


def agent_pvc_name(agent_id: str) -> str:
    return f"agent-{agent_id}-workspace"


def agent_pv_name(agent_id: str) -> str:
    return f"agent-{agent_id}-workspace"


def agent_pv_host_path(agent_id: str) -> str:
    return f"{PV_HOST_ROOT}/{agent_id}"


def agent_network_policy_name(agent_id: str) -> str:
    return f"agent-{agent_id}-egress"


def agent_scaledobject_name(agent_id: str) -> str:
    return f"agent-{agent_id}"


def agent_service_account_name(agent_id: str, sa_name: str | None = None) -> str:
    if sa_name and sa_name != DEFAULT_SA_NAME:
        return sa_name
    return DEFAULT_SA_NAME


def agent_label_selector(agent_id: str) -> str:
    return f"{LABEL_AGENT_ID}={agent_id}"


def runtime_label_selector() -> str:
    return f"{LABEL_ROLE}={ROLE_RUNTIME}"

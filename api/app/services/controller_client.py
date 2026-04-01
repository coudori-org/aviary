"""HTTP client for the Agent Controller service.

Thin wrapper over the Controller REST API. All K8s operations go through here —
the API server has no direct K8s dependency.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def init_client() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.agent_controller_url,
        timeout=30,
    )
    logger.info("Controller client initialized → %s", settings.agent_controller_url)


async def close_client() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Controller client not initialized — call init_client() first")
    return _client


# ── Namespace operations ──────────────────────────────────────


async def create_namespace(
    agent_id: str,
    owner_id: str,
    instruction: str,
    tools: list,
    policy: dict,
    mcp_servers: list,
) -> str:
    """Create agent namespace + all K8s resources. Returns namespace name."""
    resp = await _get_client().post("/v1/namespaces", json={
        "agent_id": agent_id,
        "owner_id": owner_id,
        "instruction": instruction,
        "tools": tools,
        "policy": policy,
        "mcp_servers": mcp_servers,
    })
    resp.raise_for_status()
    return resp.json()["namespace"]


async def update_namespace_config(
    namespace: str,
    instruction: str,
    tools: list,
    policy: dict,
    mcp_servers: list,
) -> None:
    """Update the agent ConfigMap."""
    resp = await _get_client().put(f"/v1/namespaces/{namespace}/config", json={
        "instruction": instruction,
        "tools": tools,
        "policy": policy,
        "mcp_servers": mcp_servers,
    })
    resp.raise_for_status()


async def update_network_policy(namespace: str, policy: dict) -> None:
    """Update the NetworkPolicy for an agent namespace."""
    resp = await _get_client().put(f"/v1/namespaces/{namespace}/network-policy", json={
        "policy": policy,
    })
    resp.raise_for_status()


async def delete_namespace(agent_id: str) -> None:
    """Delete the entire agent namespace."""
    resp = await _get_client().delete(f"/v1/namespaces/{agent_id}")
    resp.raise_for_status()


# ── Deployment operations ─────────────────────────────────────


async def ensure_deployment(
    namespace: str,
    agent_id: str,
    owner_id: str,
    instruction: str,
    tools: list,
    policy: dict,
    mcp_servers: list,
    min_pods: int = 1,
    max_pods: int = 3,
) -> dict:
    """Ensure Deployment + Service + PVC exist. Returns {namespace, created}."""
    resp = await _get_client().post(f"/v1/deployments/{namespace}/ensure", json={
        "agent_id": agent_id,
        "owner_id": owner_id,
        "instruction": instruction,
        "tools": tools,
        "policy": policy,
        "mcp_servers": mcp_servers,
        "min_pods": min_pods,
        "max_pods": max_pods,
    })
    resp.raise_for_status()
    return resp.json()


async def get_deployment_status(namespace: str) -> dict:
    """Get replica counts for a deployment."""
    resp = await _get_client().get(f"/v1/deployments/{namespace}/status")
    resp.raise_for_status()
    return resp.json()


async def wait_for_ready(namespace: str, timeout: int = 90) -> bool:
    """Long-poll until deployment is ready. Returns True if ready."""
    resp = await _get_client().get(
        f"/v1/deployments/{namespace}/ready",
        params={"timeout": timeout},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json()["ready"]


async def scale_deployment(namespace: str, replicas: int, min_pods: int, max_pods: int) -> None:
    """Scale the agent deployment."""
    resp = await _get_client().patch(f"/v1/deployments/{namespace}/scale", json={
        "replicas": replicas,
        "min_pods": min_pods,
        "max_pods": max_pods,
    })
    resp.raise_for_status()


async def scale_to_zero(namespace: str) -> None:
    """Scale agent deployment to 0 replicas."""
    resp = await _get_client().patch(f"/v1/deployments/{namespace}/scale-to-zero")
    resp.raise_for_status()


async def delete_deployment(namespace: str) -> None:
    """Delete Deployment + Service + PVC."""
    resp = await _get_client().delete(f"/v1/deployments/{namespace}")
    resp.raise_for_status()


async def cleanup_session_workspace(namespace: str, session_id: str) -> None:
    """Delete a session's workspace directory on the PVC. Best-effort — pod may be down."""
    try:
        resp = await _get_client().delete(
            f"/v1/deployments/{namespace}/sessions/{session_id}",
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        logger.info(
            "Session workspace cleanup skipped for %s in %s (non-critical)",
            session_id, namespace,
        )


async def rolling_restart(namespace: str) -> None:
    """Trigger rolling restart."""
    resp = await _get_client().post(f"/v1/deployments/{namespace}/restart")
    resp.raise_for_status()


async def get_pod_metrics(namespace: str) -> dict:
    """Query pod metrics for scaling decisions."""
    resp = await _get_client().get(f"/v1/pods/{namespace}/metrics")
    resp.raise_for_status()
    return resp.json()


# ── Streaming ─────────────────────────────────────────────────


def get_stream_url(namespace: str) -> str:
    """Get the full URL for SSE streaming to a runtime Pod."""
    return f"{settings.agent_controller_url}/v1/stream/{namespace}/message"


async def abort_stream(namespace: str, session_id: str) -> None:
    """Send abort request to the runtime Pod."""
    try:
        resp = await _get_client().post(
            f"/v1/stream/{namespace}/abort/{session_id}",
            timeout=5,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Failed to send abort for session %s in %s", session_id, namespace)


# ── Egress ────────────────────────────────────────────────────


async def invalidate_egress_cache(agent_id: str) -> None:
    """Invalidate egress proxy cache for an agent. Non-critical."""
    try:
        await _get_client().post(f"/v1/egress/invalidate/{agent_id}")
    except Exception:
        logger.debug("Egress cache invalidation failed for agent %s (non-critical)", agent_id)

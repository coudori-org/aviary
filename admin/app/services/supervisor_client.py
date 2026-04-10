"""Agent Supervisor HTTP client for the admin service.

Direct access to K8s-level operations via the supervisor's namespace/deployment API.
Unlike the API server's abstracted client, the admin service uses the full supervisor API.
"""

import logging

from aviary_shared.http import ServiceClient
from aviary_shared.naming import agent_namespace

from app.config import settings

logger = logging.getLogger(__name__)

_supervisor = ServiceClient(base_url=settings.agent_supervisor_url)


async def init_client() -> None:
    await _supervisor.init()


async def close_client() -> None:
    await _supervisor.close()


# ── Namespace operations ──────────────────────────────────────


async def create_namespace(
    agent_id: str, owner_id: str, policy: dict,
) -> str:
    resp = await _supervisor.client.post("/v1/namespaces", json={
        "agent_id": agent_id, "owner_id": owner_id,
        "policy": policy,
    })
    resp.raise_for_status()
    return resp.json()["namespace"]


async def update_network_policy(namespace: str, policy: dict) -> None:
    resp = await _supervisor.client.put(
        f"/v1/namespaces/{namespace}/network-policy", json={"policy": policy},
    )
    resp.raise_for_status()


async def delete_namespace(agent_id: str) -> None:
    resp = await _supervisor.client.delete(f"/v1/namespaces/{agent_id}")
    resp.raise_for_status()


# ── Deployment operations ─────────────────────────────────────


async def ensure_deployment(
    namespace: str, agent_id: str, owner_id: str,
    policy: dict, min_pods: int = 1, max_pods: int = 3,
) -> dict:
    resp = await _supervisor.client.post(f"/v1/deployments/{namespace}/ensure", json={
        "agent_id": agent_id, "owner_id": owner_id,
        "policy": policy,
        "min_pods": min_pods, "max_pods": max_pods,
    })
    resp.raise_for_status()
    return resp.json()


async def get_deployment_status(namespace: str) -> dict:
    resp = await _supervisor.client.get(f"/v1/deployments/{namespace}/status")
    resp.raise_for_status()
    return resp.json()


async def scale_deployment(namespace: str, replicas: int, min_pods: int, max_pods: int) -> None:
    resp = await _supervisor.client.patch(f"/v1/deployments/{namespace}/scale", json={
        "replicas": replicas, "min_pods": min_pods, "max_pods": max_pods,
    })
    resp.raise_for_status()


async def scale_to_zero(namespace: str) -> None:
    resp = await _supervisor.client.patch(f"/v1/deployments/{namespace}/scale-to-zero")
    resp.raise_for_status()


async def delete_deployment(namespace: str) -> None:
    resp = await _supervisor.client.delete(f"/v1/deployments/{namespace}")
    resp.raise_for_status()


async def rolling_restart(namespace: str) -> None:
    resp = await _supervisor.client.post(f"/v1/deployments/{namespace}/restart")
    resp.raise_for_status()


async def get_pod_metrics(namespace: str) -> dict:
    resp = await _supervisor.client.get(f"/v1/pods/{namespace}/metrics")
    resp.raise_for_status()
    return resp.json()

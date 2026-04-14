"""Agent Supervisor HTTP client for the admin service (agent_id-centric)."""

from __future__ import annotations

import logging

from aviary_shared.http import ServiceClient

from app.config import settings

logger = logging.getLogger(__name__)

_supervisor = ServiceClient(base_url=settings.agent_supervisor_url)


async def init_client() -> None:
    await _supervisor.init()


async def close_client() -> None:
    await _supervisor.close()


async def ensure_agent(
    agent_id: str, owner_id: str,
    image: str | None = None,
    sa_name: str = "agent-default-sa",
    min_pods: int = 0,
    max_pods: int = 3,
    cpu_limit: str | None = None,
    memory_limit: str | None = None,
) -> None:
    resp = await _supervisor.client.post(
        f"/v1/agents/{agent_id}/ensure",
        json={
            "owner_id": owner_id,
            "image": image,
            "sa_name": sa_name,
            "min_pods": min_pods,
            "max_pods": max_pods,
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
        },
    )
    resp.raise_for_status()


async def delete_agent(agent_id: str) -> None:
    resp = await _supervisor.client.delete(f"/v1/agents/{agent_id}/deployment")
    resp.raise_for_status()


async def get_deployment_status(agent_id: str) -> dict:
    resp = await _supervisor.client.get(f"/v1/agents/{agent_id}/status")
    resp.raise_for_status()
    return resp.json()


async def scale_deployment(agent_id: str, replicas: int) -> None:
    resp = await _supervisor.client.patch(
        f"/v1/agents/{agent_id}/scale", json={"replicas": replicas},
    )
    resp.raise_for_status()


async def scale_to_zero(agent_id: str) -> None:
    resp = await _supervisor.client.patch(f"/v1/agents/{agent_id}/scale-to-zero")
    resp.raise_for_status()


async def rolling_restart(agent_id: str) -> None:
    resp = await _supervisor.client.post(f"/v1/agents/{agent_id}/restart")
    resp.raise_for_status()


async def bind_identity(
    agent_id: str, sg_refs: list[str], sa_name: str = "agent-default-sa",
) -> None:
    """Apply egress identity (SA + SG/profile refs). Multiple refs merge as in AWS SG."""
    resp = await _supervisor.client.put(
        f"/v1/agents/{agent_id}/identity",
        json={"sa_name": sa_name, "sg_refs": sg_refs},
    )
    resp.raise_for_status()


async def unbind_identity(agent_id: str) -> None:
    resp = await _supervisor.client.delete(f"/v1/agents/{agent_id}/identity")
    resp.raise_for_status()


async def get_pod_metrics(agent_id: str) -> dict:
    resp = await _supervisor.client.get(f"/v1/agents/{agent_id}/metrics")
    resp.raise_for_status()
    return resp.json()

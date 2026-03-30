"""Custom auto-scaler for agent Deployments.

Runs as a background task in the API server. Periodically checks active
agent deployments and adjusts replica counts based on session load.

Scaling metrics come from the runtime Pod's GET /metrics endpoint,
queried via K8s API proxy to individual Pods.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db.models import Agent
from app.services import deployment_service, k8s_service

logger = logging.getLogger(__name__)


async def scaling_loop():
    """Periodic scaling check for all active agent deployments."""
    interval = settings.scaling_check_interval

    while True:
        await asyncio.sleep(interval)
        try:
            await _check_and_scale()
        except Exception:
            logger.warning("Scaling loop iteration failed", exc_info=True)


async def _check_and_scale():
    """Check all active agents and adjust their deployment scale."""
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.deployment_active.is_(True),
                Agent.status == "active",
            )
        )
        agents = result.scalars().all()

    for agent in agents:
        try:
            await _scale_agent(agent)
        except Exception:
            logger.warning("Failed to scale agent %s", agent.id, exc_info=True)


async def _scale_agent(agent: Agent):
    """Evaluate and adjust scaling for a single agent."""
    if not agent.namespace:
        return

    # Get current deployment status
    dep_status = await deployment_service.get_deployment_status(agent)
    current_replicas = dep_status.get("replicas", 0)
    ready_replicas = dep_status.get("ready_replicas", 0)

    if current_replicas == 0:
        return  # Scaled to zero (idle), don't auto-scale

    # Query metrics from pods via K8s API
    total_active = 0
    total_streaming = 0
    pods_queried = 0

    try:
        pod_list = await k8s_service._k8s_apply(
            "GET",
            f"/api/v1/namespaces/{agent.namespace}/pods?labelSelector=aviary/role=agent-runtime",
        )
        pods = pod_list.get("items", [])

        for pod in pods:
            pod_name = pod.get("metadata", {}).get("name")
            phase = pod.get("status", {}).get("phase")
            if not pod_name or phase != "Running":
                continue

            try:
                metrics = await k8s_service._k8s_apply(
                    "GET",
                    f"/api/v1/namespaces/{agent.namespace}/pods/{pod_name}:3000/proxy/metrics",
                )
                total_active += metrics.get("sessions_active", 0)
                total_streaming += metrics.get("sessions_streaming", 0)
                pods_queried += 1
            except Exception:
                pass  # Pod might not be ready yet
    except Exception:
        return

    if pods_queried == 0:
        return

    sessions_per_pod = total_active / pods_queried

    # Scale up: if average sessions per pod exceeds threshold
    if sessions_per_pod > settings.sessions_per_pod_scale_up and current_replicas < agent.max_pods:
        new_replicas = min(current_replicas + 1, agent.max_pods)
        logger.info(
            "Scaling UP agent %s: %d -> %d replicas (%.1f sessions/pod)",
            agent.id, current_replicas, new_replicas, sessions_per_pod,
        )
        await deployment_service.scale_agent_deployment(agent, new_replicas)

    # Scale down: if average sessions per pod is below threshold
    elif sessions_per_pod < settings.sessions_per_pod_scale_down and current_replicas > agent.min_pods:
        # Don't scale down if any pod is actively streaming
        if total_streaming > 0:
            return
        new_replicas = max(current_replicas - 1, agent.min_pods)
        logger.info(
            "Scaling DOWN agent %s: %d -> %d replicas (%.1f sessions/pod)",
            agent.id, current_replicas, new_replicas, sessions_per_pod,
        )
        await deployment_service.scale_agent_deployment(agent, new_replicas)

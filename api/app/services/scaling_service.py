"""Custom auto-scaler for agent Deployments.

Runs as a background task in the API server. Periodically checks active
agent deployments and adjusts replica counts based on session load.
Queries pod metrics and scales deployments via the Agent Controller.
"""

import asyncio
import logging

from sqlalchemy import select

from app.config import settings
from app.db.models import Agent
from app.services import controller_client

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

    # Get current deployment status via Controller
    dep_status = await controller_client.get_deployment_status(agent.namespace)
    current_replicas = dep_status.get("replicas", 0)

    if current_replicas == 0:
        return  # Scaled to zero (idle), don't auto-scale

    # Query pod metrics via Controller
    metrics = await controller_client.get_pod_metrics(agent.namespace)
    total_active = metrics.get("total_active", 0)
    total_streaming = metrics.get("total_streaming", 0)
    pods_queried = metrics.get("pods_queried", 0)

    if pods_queried == 0:
        return

    sessions_per_pod = total_active / pods_queried

    # Scale up
    if sessions_per_pod > settings.sessions_per_pod_scale_up and current_replicas < agent.max_pods:
        new_replicas = min(current_replicas + 1, agent.max_pods)
        logger.info(
            "Scaling UP agent %s: %d -> %d replicas (%.1f sessions/pod)",
            agent.id, current_replicas, new_replicas, sessions_per_pod,
        )
        await controller_client.scale_deployment(
            agent.namespace, new_replicas, agent.min_pods, agent.max_pods
        )

    # Scale down
    elif sessions_per_pod < settings.sessions_per_pod_scale_down and current_replicas > agent.min_pods:
        if total_streaming > 0:
            return
        new_replicas = max(current_replicas - 1, agent.min_pods)
        logger.info(
            "Scaling DOWN agent %s: %d -> %d replicas (%.1f sessions/pod)",
            agent.id, current_replicas, new_replicas, sessions_per_pod,
        )
        await controller_client.scale_deployment(
            agent.namespace, new_replicas, agent.min_pods, agent.max_pods
        )

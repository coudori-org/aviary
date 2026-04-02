"""Auto-scaling and idle cleanup for agent deployments.

Running state is derived from the controller (live K8s status).
Idle duration is based on Agent.last_activity_at (updated by the API server on every chat message).
"""

import asyncio
import logging
import time

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.services import controller_client

logger = logging.getLogger(__name__)


async def scaling_loop() -> None:
    """Periodically check agent deployments and scale based on session load."""
    while True:
        await asyncio.sleep(settings.scaling_check_interval)
        try:
            await _check_and_scale()
        except Exception:
            logger.warning("Scaling check failed", exc_info=True)


async def _check_and_scale() -> None:
    """Query all active agents, check live status from controller, auto-scale if needed."""
    from aviary_shared.db.models import Agent

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active")
        )
        agents = result.scalars().all()

    for agent in agents:
        ns = f"agent-{agent.id}"
        try:
            status = await controller_client.get_deployment_status(ns)
            replicas = status.get("replicas", 0)
            if replicas == 0:
                continue  # Not running, skip

            await _scale_agent(str(agent.id), ns, agent.min_pods, agent.max_pods)
        except Exception:
            pass


async def _scale_agent(agent_id: str, ns: str, min_pods: int, max_pods: int) -> None:
    metrics = await controller_client.get_pod_metrics(ns)
    pods_queried = metrics.get("pods_queried", 0)
    if pods_queried == 0:
        return

    total_active = metrics.get("total_active", 0)
    sessions_per_pod = total_active / pods_queried

    status = await controller_client.get_deployment_status(ns)
    current_replicas = status.get("replicas", 1)

    if sessions_per_pod > settings.sessions_per_pod_scale_up and current_replicas < max_pods:
        new_replicas = min(current_replicas + 1, max_pods)
        await controller_client.scale_deployment(ns, new_replicas, min_pods, max_pods)
        logger.info("Scaled up agent %s: %d → %d", agent_id, current_replicas, new_replicas)

    elif sessions_per_pod < settings.sessions_per_pod_scale_down and current_replicas > min_pods:
        total_streaming = metrics.get("total_streaming", 0)
        if total_streaming > 0:
            return
        new_replicas = max(current_replicas - 1, min_pods)
        await controller_client.scale_deployment(ns, new_replicas, min_pods, max_pods)
        logger.info("Scaled down agent %s: %d → %d", agent_id, current_replicas, new_replicas)


async def cleanup_idle_agents() -> int:
    """Scale down deployments idle longer than the timeout.

    Running state is checked live from the controller.
    Idle duration is based on Agent.last_activity_at (written by the API server).
    """
    from aviary_shared.db.models import Agent

    timeout_seconds = settings.default_agent_idle_timeout
    cutoff = datetime.now(timezone.utc).timestamp() - timeout_seconds

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active")
        )
        agents = result.scalars().all()

    cleaned = 0
    for agent in agents:
        ns = f"agent-{agent.id}"

        # Check if actually running via controller
        try:
            status = await controller_client.get_deployment_status(ns)
            if (status.get("replicas") or 0) == 0:
                continue
        except Exception:
            continue

        # Check idle duration from DB
        if not agent.last_activity_at:
            continue
        if agent.last_activity_at.timestamp() >= cutoff:
            continue

        try:
            await controller_client.scale_to_zero(ns)
            cleaned += 1
            logger.info("Idle cleanup: scaled down agent %s", agent.id)
        except Exception:
            logger.warning("Failed to scale down idle agent %s", agent.id, exc_info=True)

    return cleaned

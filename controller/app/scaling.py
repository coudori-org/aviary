"""Auto-scaling and idle cleanup for agent deployments.

Reads agent configuration (min_pods, max_pods, last_activity_at) from DB.
Queries live pod metrics from K8s for scaling decisions.
Updates last_activity_at in DB when agents are accessed.
"""

import asyncio
import logging

from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.k8s import k8s_apply

logger = logging.getLogger(__name__)


async def touch_activity(agent_id: str) -> None:
    """Update last_activity_at for an agent."""
    from aviary_shared.db.models import Agent

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(Agent).where(Agent.id == agent_id))
            agent = result.scalar_one_or_none()
            if agent:
                agent.last_activity_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        logger.debug("Failed to update activity for agent %s", agent_id, exc_info=True)


async def scaling_loop() -> None:
    """Periodically check running deployments and scale based on session load."""
    while True:
        await asyncio.sleep(settings.scaling_check_interval)
        try:
            await _check_and_scale()
        except Exception:
            logger.warning("Scaling check failed", exc_info=True)


async def _check_and_scale() -> None:
    from aviary_shared.db.models import Agent

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active")
        )
        agents = result.scalars().all()

    for agent in agents:
        ns = f"agent-{agent.id}"
        try:
            dep = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime"
            )
            replicas = dep.get("spec", {}).get("replicas", 0)
            if replicas == 0:
                continue
        except Exception:
            continue

        try:
            await _scale_agent(str(agent.id), ns, agent.min_pods, agent.max_pods)
        except Exception:
            pass


async def _scale_agent(agent_id: str, ns: str, min_pods: int, max_pods: int) -> None:
    # Query pod metrics
    total_active = 0
    total_streaming = 0
    pods_queried = 0

    try:
        pod_list = await k8s_apply(
            "GET", f"/api/v1/namespaces/{ns}/pods?labelSelector=aviary/role=agent-runtime",
        )
        for pod in pod_list.get("items", []):
            pod_name = pod.get("metadata", {}).get("name")
            phase = pod.get("status", {}).get("phase")
            if not pod_name or phase != "Running":
                continue
            try:
                metrics = await k8s_apply(
                    "GET", f"/api/v1/namespaces/{ns}/pods/{pod_name}:3000/proxy/metrics",
                )
                total_active += metrics.get("sessions_active", 0)
                total_streaming += metrics.get("sessions_streaming", 0)
                pods_queried += 1
            except Exception:
                pass
    except Exception:
        return

    if pods_queried == 0:
        return

    sessions_per_pod = total_active / pods_queried

    dep = await k8s_apply(
        "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime"
    )
    current_replicas = dep.get("spec", {}).get("replicas", 1)

    if sessions_per_pod > settings.sessions_per_pod_scale_up and current_replicas < max_pods:
        new_replicas = min(current_replicas + 1, max_pods)
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime",
            {"spec": {"replicas": new_replicas}},
        )
        logger.info("Scaled up agent %s: %d → %d", agent_id, current_replicas, new_replicas)

    elif sessions_per_pod < settings.sessions_per_pod_scale_down and current_replicas > min_pods:
        if total_streaming > 0:
            return
        new_replicas = max(current_replicas - 1, min_pods)
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime",
            {"spec": {"replicas": new_replicas}},
        )
        logger.info("Scaled down agent %s: %d → %d", agent_id, current_replicas, new_replicas)


async def idle_cleanup_loop() -> None:
    """Periodically scale down deployments that have been idle longer than the timeout."""
    while True:
        await asyncio.sleep(settings.idle_cleanup_interval)
        try:
            await _idle_cleanup()
        except Exception:
            logger.warning("Idle cleanup failed", exc_info=True)


async def _idle_cleanup() -> None:
    from aviary_shared.db.models import Agent

    cutoff = datetime.now(timezone.utc).timestamp() - settings.agent_idle_timeout

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active")
        )
        agents = result.scalars().all()

    cleaned = 0
    for agent in agents:
        ns = f"agent-{agent.id}"

        # Check if deployment is running
        try:
            dep = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime"
            )
            replicas = dep.get("spec", {}).get("replicas", 0)
            if replicas == 0:
                continue
        except Exception:
            continue

        # Check idle duration
        if agent.last_activity_at and agent.last_activity_at.timestamp() >= cutoff:
            continue

        # Idle — scale to zero
        try:
            await k8s_apply(
                "PATCH",
                f"/apis/apps/v1/namespaces/{ns}/deployments/agent-runtime",
                {"spec": {"replicas": 0}},
            )
            cleaned += 1
            logger.info("Idle cleanup: scaled down agent %s", agent.id)
        except Exception:
            logger.warning("Failed to scale down idle agent %s", agent.id, exc_info=True)

    if cleaned:
        logger.info("Idle cleanup: scaled down %d agent(s)", cleaned)

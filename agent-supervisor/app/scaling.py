"""Auto-scaling and idle cleanup for agent deployments."""

import asyncio
import logging

import httpx
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from aviary_shared.naming import (
    DEPLOYMENT_NAME,
    RUNTIME_PORT,
    agent_namespace,
    runtime_label_selector,
)

from app.config import settings
from app.db import async_session_factory
from app.k8s import k8s_apply

logger = logging.getLogger(__name__)


async def touch_activity(agent_id: str) -> None:
    """Update last_activity_at on the agent's policy. Failure logged at WARNING."""
    from aviary_shared.db.models import Agent, Policy

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Agent).where(Agent.id == agent_id).options(selectinload(Agent.policy))
            )
            agent = result.scalar_one_or_none()
            if not agent:
                return
            if agent.policy:
                agent.policy.last_activity_at = datetime.now(timezone.utc)
            else:
                policy = Policy(last_activity_at=datetime.now(timezone.utc))
                db.add(policy)
                await db.flush()
                agent.policy_id = policy.id
            await db.commit()
    except Exception:
        logger.warning("Failed to update activity for agent %s", agent_id, exc_info=True)


_scaling_failures = 0
_idle_cleanup_failures = 0
_LOOP_FAILURE_ESCALATION = 3


async def scaling_loop() -> None:
    """Periodically check running deployments and scale based on session load."""
    global _scaling_failures
    while True:
        await asyncio.sleep(settings.scaling_check_interval)
        try:
            await _check_and_scale()
            _scaling_failures = 0
        except Exception:
            _scaling_failures += 1
            level = logging.ERROR if _scaling_failures >= _LOOP_FAILURE_ESCALATION else logging.WARNING
            logger.log(level, "Scaling check failed (%d consecutive)", _scaling_failures, exc_info=True)


async def _check_and_scale() -> None:
    from aviary_shared.db.models import Agent

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active").options(selectinload(Agent.policy))
        )
        agents = result.scalars().all()

    for agent in agents:
        ns = agent_namespace(str(agent.id))
        min_pods = agent.policy.min_pods if agent.policy else 1
        max_pods = agent.policy.max_pods if agent.policy else 3

        try:
            dep = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                logger.warning("Deployment lookup failed for agent %s", agent.id, exc_info=True)
            continue
        except httpx.HTTPError:
            logger.warning("Deployment lookup failed for agent %s", agent.id, exc_info=True)
            continue

        if dep.get("spec", {}).get("replicas", 0) == 0:
            continue

        try:
            await _scale_agent(str(agent.id), ns, min_pods, max_pods)
        except httpx.HTTPError:
            logger.warning("Scaling failed for agent %s", agent.id, exc_info=True)


async def _scale_agent(agent_id: str, ns: str, min_pods: int, max_pods: int) -> None:
    total_active = 0
    total_streaming = 0
    pods_queried = 0
    pods_failed = 0

    try:
        pod_list = await k8s_apply(
            "GET", f"/api/v1/namespaces/{ns}/pods?labelSelector={runtime_label_selector()}",
        )
    except httpx.HTTPError:
        logger.warning("Pod list query failed for agent %s", agent_id, exc_info=True)
        return

    for pod in pod_list.get("items", []):
        pod_name = pod.get("metadata", {}).get("name")
        phase = pod.get("status", {}).get("phase")
        if not pod_name or phase != "Running":
            continue
        try:
            metrics = await k8s_apply(
                "GET", f"/api/v1/namespaces/{ns}/pods/{pod_name}:{RUNTIME_PORT}/proxy/metrics",
            )
            total_active += metrics.get("sessions_active", 0)
            total_streaming += metrics.get("sessions_streaming", 0)
            pods_queried += 1
        except httpx.HTTPError:
            pods_failed += 1
            logger.warning("Metrics fetch failed for pod %s", pod_name, exc_info=True)

    if pods_queried == 0:
        if pods_failed > 0:
            logger.error("All pod metrics queries failed for agent %s — skipping scale decision", agent_id)
        return

    sessions_per_pod = total_active / pods_queried

    dep = await k8s_apply(
        "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}"
    )
    current_replicas = dep.get("spec", {}).get("replicas", 1)

    if sessions_per_pod > settings.sessions_per_pod_scale_up and current_replicas < max_pods:
        new_replicas = min(current_replicas + 1, max_pods)
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}",
            {"spec": {"replicas": new_replicas}},
        )
        logger.info("Scaled up agent %s: %d → %d", agent_id, current_replicas, new_replicas)

    elif sessions_per_pod < settings.sessions_per_pod_scale_down and current_replicas > min_pods:
        if total_streaming > 0:
            return
        new_replicas = max(current_replicas - 1, min_pods)
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}",
            {"spec": {"replicas": new_replicas}},
        )
        logger.info("Scaled down agent %s: %d → %d", agent_id, current_replicas, new_replicas)


async def idle_cleanup_loop() -> None:
    """Periodically scale down deployments that have been idle longer than the timeout."""
    global _idle_cleanup_failures
    while True:
        await asyncio.sleep(settings.idle_cleanup_interval)
        try:
            await _idle_cleanup()
            _idle_cleanup_failures = 0
        except Exception:
            _idle_cleanup_failures += 1
            level = logging.ERROR if _idle_cleanup_failures >= _LOOP_FAILURE_ESCALATION else logging.WARNING
            logger.log(level, "Idle cleanup failed (%d consecutive)", _idle_cleanup_failures, exc_info=True)


async def _idle_cleanup() -> None:
    from aviary_shared.db.models import Agent

    cutoff = datetime.now(timezone.utc).timestamp() - settings.agent_idle_timeout

    async with async_session_factory() as db:
        result = await db.execute(
            select(Agent).where(Agent.status == "active").options(selectinload(Agent.policy))
        )
        agents = result.scalars().all()

    cleaned = 0
    for agent in agents:
        ns = agent_namespace(str(agent.id))

        try:
            dep = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                logger.warning("Deployment lookup failed for agent %s", agent.id, exc_info=True)
            continue
        except httpx.HTTPError:
            logger.warning("Deployment lookup failed for agent %s", agent.id, exc_info=True)
            continue

        if dep.get("spec", {}).get("replicas", 0) == 0:
            continue

        last_activity = agent.policy.last_activity_at if agent.policy else None
        if last_activity and last_activity.timestamp() >= cutoff:
            continue

        try:
            await k8s_apply(
                "PATCH",
                f"/apis/apps/v1/namespaces/{ns}/deployments/{DEPLOYMENT_NAME}",
                {"spec": {"replicas": 0}},
            )
            cleaned += 1
            logger.info("Idle cleanup: scaled down agent %s", agent.id)
        except httpx.HTTPError:
            logger.warning("Failed to scale down idle agent %s", agent.id, exc_info=True)

    if cleaned:
        logger.info("Idle cleanup: scaled down %d agent(s)", cleaned)

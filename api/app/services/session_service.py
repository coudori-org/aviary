"""Session business logic: CRUD, Pod lifecycle management, idle timeout."""

import json
import logging
import os
import uuid

from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Agent, Message, Session, SessionParticipant, User
from app.services import k8s_service


@lru_cache(maxsize=1)
def _get_host_gateway_ip() -> str:
    """Get the Docker/K3s host gateway IP for Pod → host communication.

    This allows session Pods to reach Ollama/vLLM running on the host.
    Falls back to a common Docker gateway if detection fails.
    """
    # Try to read from environment (set in docker-compose)
    gateway = os.environ.get("HOST_GATEWAY_IP")
    if gateway:
        return gateway
    # Default Docker bridge gateway
    return "172.17.0.1"


async def _cleanup_session_pod(namespace: str, pod_name: str) -> None:
    """Best-effort cleanup of a stale session Pod.

    Only deletes the Pod — PVC is preserved so that workspace files
    (/workspace) survive across container restarts.
    """
    try:
        await k8s_service._k8s_apply("DELETE", f"/api/v1/namespaces/{namespace}/pods/{pod_name}")
    except Exception:
        pass
    import asyncio
    await asyncio.sleep(1)


async def _pod_exists(namespace: str, pod_name: str) -> bool:
    """Check if a Pod is usable in K8s.

    Returns False for: not found, Terminating, Failed, Succeeded,
    or Pending for more than 30 seconds (likely stuck due to stale PVC/node).
    """
    try:
        result = await k8s_service._k8s_apply("GET", f"/api/v1/namespaces/{namespace}/pods/{pod_name}")
        # Pod with deletionTimestamp is terminating
        if result.get("metadata", {}).get("deletionTimestamp"):
            return False
        phase = result.get("status", {}).get("phase", "")
        if phase == "Running":
            return True
        if phase == "Pending":
            # Check if it's been Pending too long (stuck scheduling)
            creation = result.get("metadata", {}).get("creationTimestamp", "")
            if creation:
                from datetime import datetime, timezone
                try:
                    created_at = datetime.fromisoformat(creation.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - created_at).total_seconds()
                    if age > 30:
                        return False  # Stuck Pending — treat as dead
                except Exception:
                    pass
            return True  # Just created, give it a chance
        return False
    except Exception:
        return False

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    user: User,
    agent: Agent,
    session_type: str = "private",
    team_id: uuid.UUID | None = None,
) -> Session:
    """Create a new chat session."""
    session = Session(
        agent_id=agent.id,
        type=session_type,
        created_by=user.id,
        team_id=team_id,
    )
    db.add(session)
    await db.flush()

    # Add creator as participant
    participant = SessionParticipant(
        session_id=session.id,
        user_id=user.id,
    )
    db.add(participant)
    await db.flush()

    return session


async def get_session(db: AsyncSession, session_id: uuid.UUID) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def list_sessions_for_agent(
    db: AsyncSession, user: User, agent_id: uuid.UUID
) -> list[Session]:
    """List sessions for an agent that the user can access."""
    result = await db.execute(
        select(Session)
        .join(SessionParticipant, SessionParticipant.session_id == Session.id)
        .where(
            Session.agent_id == agent_id,
            Session.status == "active",
            SessionParticipant.user_id == user.id,
        )
        .order_by(Session.created_at.desc())
    )
    return list(result.scalars().all())


async def get_session_messages(
    db: AsyncSession, session_id: uuid.UUID, limit: int = 100
) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    sender_type: str,
    content: str,
    sender_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> Message:
    """Save a message and update session timestamp."""
    msg = Message(
        session_id=session_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        metadata_json=metadata or {},
    )
    db.add(msg)

    # Update last_message_at
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one()
    session.last_message_at = datetime.now(timezone.utc)

    # Auto-set title from first message
    if session.title is None and sender_type == "user":
        session.title = content[:100]

    await db.flush()
    return msg


async def invite_user_to_session(
    db: AsyncSession,
    session: Session,
    invitee: User,
    invited_by: User,
) -> SessionParticipant:
    """Invite a user to a session."""
    participant = SessionParticipant(
        session_id=session.id,
        user_id=invitee.id,
        invited_by=invited_by.id,
    )
    db.add(participant)
    await db.flush()
    return participant


async def is_session_participant(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def ensure_session_pod(
    db: AsyncSession, session: Session, agent: Agent
) -> str:
    """Ensure a healthy Pod is running for the session.

    Self-healing: if the recorded Pod is gone (stale after restart, terminated, etc.),
    the reference is cleared and a new Pod is spawned. No external cleanup needed.
    """
    from app.services import redis_service

    if not agent.namespace:
        raise RuntimeError(f"Agent {agent.id} has no K8s namespace")

    pod_name = session.pod_name

    # If we think a Pod exists, verify it's actually alive in K8s
    if pod_name:
        if await _pod_exists(agent.namespace, pod_name):
            await redis_service.cache_session_pod(str(session.id), pod_name, agent.namespace)
            return pod_name
        # Pod is gone — clear stale reference, clean up only the Pod (keep PVC for data)
        logger.info("Pod %s is stale (not found or terminating), will respawn", pod_name)
        session.pod_name = None
        await db.flush()
        await redis_service.cache_session_pod(str(session.id), None, None)
        await _cleanup_session_pod(agent.namespace, pod_name)

    # Spawn a new Pod (reuses existing PVC if present — workspace files preserved)
    pod_name = f"session-{str(session.id)[:8]}"

    # Clean up any leftover Pod with the same name (but keep PVC)
    await _cleanup_session_pod(agent.namespace, pod_name)

    try:
        await _spawn_session_pod(
            namespace=agent.namespace,
            pod_name=pod_name,
            session_id=str(session.id),
            agent_id=str(agent.id),
            policy=agent.policy,
        )
    except Exception:
        logger.error("Pod spawn failed for session %s", session.id, exc_info=True)
        raise

    session.pod_name = pod_name
    await db.flush()
    await redis_service.cache_session_pod(str(session.id), pod_name, agent.namespace)
    return pod_name


async def _spawn_session_pod(
    namespace: str,
    pod_name: str,
    session_id: str,
    agent_id: str,
    policy: dict,
) -> None:
    """Create a session Pod + PVC in K8s."""
    memory_limit = policy.get("maxMemoryPerSession", "512Mi")
    cpu_limit = policy.get("maxCpuPerSession", "500m")
    container_image = policy.get("containerImage", settings.agent_runtime_image)

    # Create PVC
    pvc_name = f"session-{session_id[:8]}"
    await k8s_service._k8s_apply("POST", f"/api/v1/namespaces/{namespace}/persistentvolumeclaims", {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {
            "name": pvc_name,
            "namespace": namespace,
            "labels": {"agentbox/session-id": session_id},
        },
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "resources": {"requests": {"storage": "1Gi"}},
            "storageClassName": "local-path",
        },
    })

    # Create Pod
    await k8s_service._k8s_apply("POST", f"/api/v1/namespaces/{namespace}/pods", {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": namespace,
            "labels": {
                "agentbox/role": "session",
                "agentbox/session-id": session_id,
            },
        },
        "spec": {
            "serviceAccountName": "session-runner",
            "restartPolicy": "Never",
            "securityContext": {
                "runAsUser": 1000,
                "runAsGroup": 1000,
                "fsGroup": 1000,
            },
            "hostAliases": [{
                "ip": _get_host_gateway_ip(),
                "hostnames": ["host.k3s.internal"],
            }],
            "containers": [{
                "name": "agent-runtime",
                "image": container_image,
                "imagePullPolicy": "Never",
                "ports": [{"containerPort": 3000}],
                "env": [
                    {"name": "SESSION_ID", "value": session_id},
                    {"name": "AGENT_ID", "value": agent_id},
                    {"name": "CREDENTIAL_PROXY_URL", "value": "http://credential-proxy.platform.svc:8080"},
                    {"name": "INFERENCE_OLLAMA_URL", "value": settings.inference_ollama_url},
                    {"name": "INFERENCE_VLLM_URL", "value": settings.inference_vllm_url},
                    {"name": "HOME", "value": "/tmp"},
                ],
                "volumeMounts": [
                    {"name": "session-workspace", "mountPath": "/workspace"},
                    {"name": "agent-config", "mountPath": "/agent/config", "readOnly": True},
                ],
                "resources": {
                    "requests": {"cpu": "250m", "memory": "256Mi"},
                    "limits": {"cpu": cpu_limit, "memory": memory_limit},
                },
                "livenessProbe": {
                    "httpGet": {"path": "/health", "port": 3000},
                    "initialDelaySeconds": 5,
                    "periodSeconds": 30,
                },
                "readinessProbe": {
                    "httpGet": {"path": "/ready", "port": 3000},
                    "initialDelaySeconds": 3,
                },
            }],
            "volumes": [
                {"name": "session-workspace", "persistentVolumeClaim": {"claimName": pvc_name}},
                {"name": "agent-config", "configMap": {"name": "agent-config"}},
            ],
        },
    })


async def cleanup_idle_sessions(db: AsyncSession) -> int:
    """Delete Pods for sessions that have been idle longer than the timeout. Returns count."""
    timeout_seconds = settings.default_session_timeout
    cutoff = datetime.now(timezone.utc).timestamp() - timeout_seconds

    result = await db.execute(
        select(Session)
        .join(Agent, Agent.id == Session.agent_id)
        .where(
            Session.pod_name.is_not(None),
            Session.status == "active",
        )
    )
    sessions = result.scalars().all()

    cleaned = 0
    for session in sessions:
        if session.last_message_at and session.last_message_at.timestamp() < cutoff:
            # Fetch agent for namespace
            agent_result = await db.execute(select(Agent).where(Agent.id == session.agent_id))
            agent = agent_result.scalar_one_or_none()
            if agent and agent.namespace and session.pod_name:
                try:
                    await k8s_service._k8s_apply(
                        "DELETE",
                        f"/api/v1/namespaces/{agent.namespace}/pods/{session.pod_name}",
                    )
                except Exception:
                    logger.warning("Failed to delete idle pod %s", session.pod_name, exc_info=True)

                session.pod_name = None
                # Invalidate Redis cache
                from app.services import redis_service as _redis
                await _redis.cache_session_pod(str(session.id), None, None)
                cleaned += 1

    if cleaned:
        await db.flush()
    return cleaned

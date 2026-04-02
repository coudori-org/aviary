"""Agent Controller client — abstract orchestration interface.

The API server treats this as a black-box agent runtime manager.
No infrastructure-specific concepts leak into the API layer.
All resource provisioning details are delegated to the controller.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _namespace(agent_id: str) -> str:
    """Derive the controller's internal resource identifier from agent ID."""
    return f"agent-{agent_id}"


async def init_client() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.agent_controller_url,
        timeout=30,
    )
    logger.info("Agent controller client initialized → %s", settings.agent_controller_url)


async def close_client() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Agent controller client not initialized — call init_client() first")
    return _client


async def register_agent(agent_id: str, owner_id: str, config: dict) -> None:
    """Register a new agent with the controller.

    The controller provisions runtime resources with secure defaults
    (all network blocked, basic resource limits).

    config keys: instruction, tools, mcp_servers
    """
    resp = await _get_client().post("/v1/namespaces", json={
        "agent_id": agent_id,
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "policy": {},  # Secure defaults — no egress, basic resources
        "mcp_servers": config.get("mcp_servers", []),
    })
    resp.raise_for_status()


async def unregister_agent(agent_id: str) -> None:
    """Remove all agent resources from the controller."""
    ns = _namespace(agent_id)

    # Delete runtime first, then the namespace
    try:
        resp = await _get_client().delete(f"/v1/deployments/{ns}")
        resp.raise_for_status()
    except Exception:
        logger.info("Runtime cleanup skipped for agent %s (may not exist)", agent_id)

    try:
        resp = await _get_client().delete(f"/v1/namespaces/{agent_id}")
        resp.raise_for_status()
    except Exception:
        logger.info("Namespace cleanup skipped for agent %s (may not exist)", agent_id)


async def ensure_agent_running(agent_id: str, owner_id: str, config: dict) -> None:
    """Ensure agent is running and ready to receive messages.

    Lazy — creates resources with secure defaults if they don't exist yet.

    config keys: instruction, tools, mcp_servers
    """
    ns = _namespace(agent_id)
    resp = await _get_client().post(f"/v1/deployments/{ns}/ensure", json={
        "agent_id": agent_id,
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "policy": {},  # Secure defaults
        "mcp_servers": config.get("mcp_servers", []),
        "min_pods": 1,
        "max_pods": 1,
    })
    resp.raise_for_status()


async def check_agent_ready(agent_id: str) -> bool:
    """Check if agent has ready instances. Returns True if ready, False otherwise."""
    ns = _namespace(agent_id)
    try:
        resp = await _get_client().get(f"/v1/deployments/{ns}/status")
        resp.raise_for_status()
        data = resp.json()
        return (data.get("ready_replicas") or 0) >= 1
    except Exception:
        return False


async def wait_for_agent_ready(agent_id: str, timeout: int = 90) -> bool:
    """Block until agent is ready or timeout. Returns True if ready."""
    ns = _namespace(agent_id)
    resp = await _get_client().get(
        f"/v1/deployments/{ns}/ready",
        params={"timeout": timeout},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json()["ready"]


def get_stream_url(agent_id: str) -> str:
    """Get the SSE stream URL for sending messages to an agent."""
    ns = _namespace(agent_id)
    return f"{settings.agent_controller_url}/v1/stream/{ns}/message"


async def abort_session(agent_id: str, session_id: str) -> None:
    """Abort an active session's stream."""
    ns = _namespace(agent_id)
    try:
        resp = await _get_client().post(
            f"/v1/stream/{ns}/abort/{session_id}",
            timeout=5,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Failed to send abort for session %s (agent %s)", session_id, agent_id)


async def cleanup_session(agent_id: str, session_id: str) -> None:
    """Clean up session workspace. Best-effort — agent may be offline."""
    ns = _namespace(agent_id)
    try:
        resp = await _get_client().delete(
            f"/v1/deployments/{ns}/sessions/{session_id}",
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        logger.info(
            "Session workspace cleanup skipped for %s (agent %s, non-critical)",
            session_id, agent_id,
        )


async def health_check() -> bool:
    """Check if the agent controller is reachable."""
    try:
        cc = _get_client()
        resp = await cc.get("/v1/health")
        return resp.status_code == 200
    except Exception:
        return False

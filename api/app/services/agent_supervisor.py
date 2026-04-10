"""Agent Supervisor client — abstract orchestration interface.

The API server treats this as a black-box agent runtime manager.
All operations use simple agent_id / session_id identifiers.
No infrastructure-specific concepts leak into the API layer.
"""

import logging

import httpx

from aviary_shared.http import ServiceClient

from app.config import settings

logger = logging.getLogger(__name__)

_supervisor = ServiceClient(base_url=settings.agent_supervisor_url)


async def init_client() -> None:
    await _supervisor.init()


async def close_client() -> None:
    await _supervisor.close()


async def register_agent(agent_id: str, owner_id: str, config: dict) -> None:
    """Register a new agent. Supervisor provisions resources with secure defaults."""
    resp = await _supervisor.client.post(f"/v1/agents/{agent_id}/register", json={
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "mcp_servers": config.get("mcp_servers", []),
    })
    resp.raise_for_status()


async def unregister_agent(agent_id: str) -> None:
    """Remove all agent resources."""
    resp = await _supervisor.client.delete(f"/v1/agents/{agent_id}")
    resp.raise_for_status()


async def ensure_agent_running(agent_id: str, owner_id: str, config: dict) -> None:
    """Ensure agent is running. Lazily creates resources if needed."""
    resp = await _supervisor.client.post(f"/v1/agents/{agent_id}/run", json={
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "mcp_servers": config.get("mcp_servers", []),
    })
    resp.raise_for_status()


async def check_agent_ready(agent_id: str) -> bool:
    """Check if agent has ready instances."""
    try:
        resp = await _supervisor.client.get(f"/v1/agents/{agent_id}/ready")
        resp.raise_for_status()
        return resp.json().get("ready", False)
    except httpx.HTTPError:  # Best-effort: readiness check is non-critical
        return False


async def wait_for_agent_ready(agent_id: str, timeout: int = 90) -> bool:
    """Block until agent is ready or timeout."""
    resp = await _supervisor.client.get(
        f"/v1/agents/{agent_id}/wait",
        params={"timeout": timeout},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json()["ready"]


def get_stream_url(agent_id: str, session_id: str) -> str:
    """Get the SSE stream URL for sending a message to an agent session."""
    return f"{settings.agent_supervisor_url}/v1/agents/{agent_id}/sessions/{session_id}/message"


async def abort_session(agent_id: str, session_id: str) -> None:
    """Abort an active session's stream."""
    try:
        resp = await _supervisor.client.post(
            f"/v1/agents/{agent_id}/sessions/{session_id}/abort",
            timeout=5,
        )
        resp.raise_for_status()
    except httpx.HTTPError:  # Best-effort: abort is non-critical
        logger.warning("Failed to abort session %s (agent %s)", session_id, agent_id)


async def cleanup_session(agent_id: str, session_id: str) -> None:
    """Clean up session workspace. Best-effort."""
    try:
        resp = await _supervisor.client.delete(
            f"/v1/agents/{agent_id}/sessions/{session_id}",
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.HTTPError:  # Best-effort: workspace cleanup is non-critical
        logger.info("Session cleanup skipped for %s (agent %s, non-critical)", session_id, agent_id)


async def health_check() -> bool:
    """Check if the agent supervisor is reachable."""
    try:
        resp = await _supervisor.client.get("/v1/health")
        return resp.status_code == 200
    except httpx.HTTPError:  # Best-effort: health check probes supervisor connectivity
        return False

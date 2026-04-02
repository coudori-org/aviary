"""Agent Controller client — abstract orchestration interface.

The API server treats this as a black-box agent runtime manager.
All operations use simple agent_id / session_id identifiers.
No infrastructure-specific concepts leak into the API layer.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


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
    """Register a new agent. Controller provisions resources with secure defaults.

    config keys: instruction, tools, mcp_servers
    """
    resp = await _get_client().post(f"/v1/agents/{agent_id}/register", json={
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "mcp_servers": config.get("mcp_servers", []),
    })
    resp.raise_for_status()


async def unregister_agent(agent_id: str) -> None:
    """Remove all agent resources."""
    resp = await _get_client().delete(f"/v1/agents/{agent_id}")
    resp.raise_for_status()


async def ensure_agent_running(agent_id: str, owner_id: str, config: dict) -> None:
    """Ensure agent is running. Lazily creates resources if needed.

    config keys: instruction, tools, mcp_servers
    """
    resp = await _get_client().post(f"/v1/agents/{agent_id}/run", json={
        "owner_id": owner_id,
        "instruction": config.get("instruction", ""),
        "tools": config.get("tools", []),
        "mcp_servers": config.get("mcp_servers", []),
    })
    resp.raise_for_status()


async def check_agent_ready(agent_id: str) -> bool:
    """Check if agent has ready instances."""
    try:
        resp = await _get_client().get(f"/v1/agents/{agent_id}/ready")
        resp.raise_for_status()
        return resp.json().get("ready", False)
    except Exception:
        return False


async def wait_for_agent_ready(agent_id: str, timeout: int = 90) -> bool:
    """Block until agent is ready or timeout."""
    resp = await _get_client().get(
        f"/v1/agents/{agent_id}/wait",
        params={"timeout": timeout},
        timeout=timeout + 10,
    )
    resp.raise_for_status()
    return resp.json()["ready"]


def get_stream_url(agent_id: str, session_id: str) -> str:
    """Get the SSE stream URL for sending a message to an agent session."""
    return f"{settings.agent_controller_url}/v1/agents/{agent_id}/sessions/{session_id}/message"


async def abort_session(agent_id: str, session_id: str) -> None:
    """Abort an active session's stream."""
    try:
        resp = await _get_client().post(
            f"/v1/agents/{agent_id}/sessions/{session_id}/abort",
            timeout=5,
        )
        resp.raise_for_status()
    except Exception:
        logger.warning("Failed to abort session %s (agent %s)", session_id, agent_id)


async def cleanup_session(agent_id: str, session_id: str) -> None:
    """Clean up session workspace. Best-effort."""
    try:
        resp = await _get_client().delete(
            f"/v1/agents/{agent_id}/sessions/{session_id}",
            timeout=10,
        )
        resp.raise_for_status()
    except Exception:
        logger.info("Session cleanup skipped for %s (agent %s, non-critical)", session_id, agent_id)


async def health_check() -> bool:
    """Check if the agent controller is reachable."""
    try:
        resp = await _get_client().get("/v1/health")
        return resp.status_code == 200
    except Exception:
        return False

"""Agent-to-Agent (A2A) HTTP endpoint.

Called by runtime A2A tools to invoke sub-agents through the normal API flow.
Uses internal API key authentication (not user JWT) since the runtime is a
trusted internal service and user tokens may expire during long sessions.

Streams the sub-agent's response as SSE while simultaneously publishing
tool_use/tool_result events to the parent session's Redis pub/sub channel
(tagged with parent_tool_use_id) for frontend inline rendering.
"""

import json
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.services import acl_service, agent_service, agent_supervisor, redis_service
from app.services.stream.manager import _build_mcp_config, _fetch_user_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


class A2AMessageRequest(BaseModel):
    content: str
    session_id: str
    parent_tool_use_id: str
    user_external_id: str


def _verify_internal_key(x_internal_key: str = Header(..., alias="X-Internal-Key")) -> str:
    """Verify the internal API key for service-to-service calls."""
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return x_internal_key


@router.post("/{agent_slug}/message")
async def a2a_message(
    agent_slug: str,
    body: A2AMessageRequest,
    _key: str = Depends(_verify_internal_key),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a sub-agent and stream the response.

    Authenticated via internal API key (not user JWT) since runtime is a
    trusted service and user tokens expire during long sessions.
    """
    # 1. Resolve user by external_id
    result = await db.execute(
        select(User).where(User.external_id == body.user_external_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # 2. Resolve agent by slug + ACL check
    agent = await agent_service.get_agent_by_slug(db, agent_slug)
    if not agent or agent.status != "active":
        raise HTTPException(status_code=404, detail=f"Agent '{agent_slug}' not found")

    try:
        await acl_service.check_agent_permission(db, user, agent, "chat")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    agent_id = str(agent.id)
    session_id = body.session_id
    parent_tool_use_id = body.parent_tool_use_id

    # 3. Ensure sub-agent is running
    try:
        await agent_supervisor.ensure_agent_running(
            agent_id=agent_id,
            owner_id=str(agent.owner_id),
            config={
                "instruction": agent.instruction,
                "tools": agent.tools,
                "mcp_servers": agent.mcp_servers or [],
            },
        )
        ready = await agent_supervisor.wait_for_agent_ready(agent_id, timeout=90)
        if not ready:
            raise HTTPException(status_code=503, detail="Sub-agent did not become ready in time")
    except HTTPException:
        raise
    except httpx.HTTPError as e:
        logger.warning("Failed to ensure sub-agent running: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to start sub-agent") from e

    # 4. Fetch credentials and build config
    credentials = await _fetch_user_credentials(user.external_id)
    stream_url = agent_supervisor.get_stream_url(agent_id, session_id)

    if not stream_url:
        raise HTTPException(status_code=503, detail="Sub-agent stream URL not available")

    # 5. Stream sub-agent response — dual output
    async def generate():
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    stream_url,
                    json={
                        "content": body.content,
                        "session_id": session_id,
                        "model_config_data": agent.model_config_json,
                        "agent_config": {
                            "instruction": agent.instruction,
                            "tools": agent.tools,
                            "mcp_servers": _build_mcp_config(
                                agent_id, "", agent.mcp_servers or []
                            ),
                            "policy": agent.policy,
                            **({"credentials": credentials} if credentials else {}),
                            "is_sub_agent": True,
                        },
                    },
                    timeout=None,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        logger.error(
                            "Sub-agent stream returned %d: %s", resp.status_code, error_body
                        )
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        chunk_data = json.loads(line[6:])
                        chunk_type = chunk_data.get("type")

                        # Tag with parent_tool_use_id for frontend scoping
                        tagged = {**chunk_data, "parent_tool_use_id": parent_tool_use_id}

                        # Publish and persist tool_use/tool_result only (not text/thinking).
                        if chunk_type in ("tool_use", "tool_result"):
                            await redis_service.publish_message(session_id, tagged)
                            await redis_service.append_a2a_event(
                                session_id, parent_tool_use_id, tagged
                            )

                        # Forward SSE to the A2A tool caller
                        yield f"data: {json.dumps(chunk_data)}\n\n"

        except httpx.HTTPError:
            logger.exception("A2A stream error for agent %s", agent_slug)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

"""Background streaming task manager.

Decouples agent response streaming from WebSocket lifecycle so that:
- Streaming continues even if the client disconnects
- Chunks are buffered in Redis for replay on reconnect
- Agent response is always saved to DB on completion

Routes to agents via the Agent Supervisor's SSE proxy endpoint.
"""

import asyncio
import json
import logging
import uuid

import httpx
from sqlalchemy import select

from app.db.models import SessionParticipant
from app.db.session import async_session_factory
from app.services import agent_supervisor, redis_service, session_service, vault_service

logger = logging.getLogger(__name__)

# In-memory registry of active streaming tasks (per API server process)
_active_streams: dict[str, asyncio.Task] = {}


def _build_mcp_config(
    agent_id: str, user_token: str, legacy_mcp_servers: list
) -> dict:
    """Build MCP servers config with legacy stdio servers + gateway auth token.

    The MCP Gateway URL is NOT included here — the runtime constructs it
    from its own MCP_GATEWAY_URL env var (K8s service DNS). The API server
    only passes the user token so the runtime can authenticate.
    """
    config: dict = {}

    # Legacy stdio servers (backward compatibility)
    for srv in legacy_mcp_servers:
        config[srv["name"]] = {"command": srv["command"], "args": srv.get("args", [])}

    return config


async def _fetch_user_credentials(user_external_id: str) -> dict[str, str]:
    """Fetch user credentials from Vault for injection into agent sandbox.

    Returns a dict of credential_name → token. Missing credentials are silently
    skipped (user may not have configured them).
    """
    credentials: dict[str, str] = {}
    # GitHub token — enables git/gh CLI authentication inside the sandbox
    try:
        secret = await vault_service.read_secret(
            f"aviary/credentials/{user_external_id}/github-token"
        )
        if token := secret.get("value"):
            credentials["github_token"] = token
    except Exception:
        pass  # No GitHub token configured for this user
    return credentials


async def start_stream(
    session_id: str,
    agent_id: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    user_token: str = "",
    user_external_id: str = "",
) -> None:
    """Launch a background task that streams the agent response."""
    # Cancel any existing stream for this session
    existing = _active_streams.get(session_id)
    if existing and not existing.done():
        logger.warning("Cancelling existing stream for session %s", session_id)
        existing.cancel()

    # Clear previous stream buffer
    await redis_service.clear_stream_buffer(session_id)

    task = asyncio.create_task(
        _run_stream(
            session_id, agent_id,
            agent_model_config, agent_instruction,
            agent_tools, agent_mcp_servers, agent_policy,
            content, user_token, user_external_id,
        )
    )
    _active_streams[session_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        _active_streams.pop(session_id, None)
    task.add_done_callback(_cleanup)


def is_streaming(session_id: str) -> bool:
    """Check if a stream task is actively running for this session."""
    task = _active_streams.get(session_id)
    return task is not None and not task.done()


async def cancel_stream(session_id: str, agent_id: str | None = None) -> bool:
    """Cancel an active stream and abort the agent's session."""
    task = _active_streams.get(session_id)
    if not task or task.done():
        return False

    # 1. Send abort request to the agent via supervisor
    if agent_id:
        await agent_supervisor.abort_session(agent_id, session_id)

    # 2. Cancel the asyncio background task
    task.cancel()

    # 3. Save partial response and broadcast cancellation
    message_id: str | None = None
    try:
        partial = await redis_service.get_stream_chunks(session_id)
        partial_text = "".join(
            chunk.get("content", "") for chunk in partial if chunk.get("type") == "chunk"
        )
        if partial_text:
            async with async_session_factory() as db:
                msg = await session_service.save_message(
                    db, uuid.UUID(session_id), "agent", partial_text
                )
                await db.commit()
                message_id = str(msg.id)
    except Exception:
        logger.warning("Failed to save partial response for cancelled session %s", session_id)

    cancelled_event: dict = {"type": "cancelled"}
    if message_id:
        cancelled_event["messageId"] = message_id
    await redis_service.publish_message(session_id, cancelled_event)

    await redis_service.set_stream_status(session_id, "complete")
    await redis_service.set_session_status(session_id, "idle")
    await redis_service.clear_stream_buffer(session_id)

    return True


async def _run_stream(
    session_id: str,
    agent_id: str,
    agent_model_config: dict,
    agent_instruction: str,
    agent_tools: list,
    agent_mcp_servers: list,
    agent_policy: dict,
    content: str,
    user_token: str = "",
    user_external_id: str = "",
) -> None:
    """Execute the agent response stream as a background task."""
    session_uuid = uuid.UUID(session_id)

    await redis_service.set_stream_status(session_id, "streaming")
    await redis_service.set_session_status(session_id, "streaming")

    # Broadcast replay_start so all connected clients show the typing indicator
    await redis_service.publish_message(session_id, {"type": "replay_start"})

    # Ensure agent is running before streaming (handles pod-killed-while-chatting case)
    try:
        await agent_supervisor.ensure_agent_running(
            agent_id=agent_id,
            owner_id="",  # Not needed for re-activation
            config={
                "instruction": agent_instruction,
                "tools": agent_tools,
                "mcp_servers": agent_mcp_servers,
            },
        )
        ready = await agent_supervisor.wait_for_agent_ready(agent_id, timeout=90)
        if not ready:
            error_event = {"type": "error", "message": "Agent did not become ready in time"}
            await redis_service.publish_message(session_id, error_event)
            await redis_service.set_stream_status(session_id, "error")
            await redis_service.set_session_status(session_id, "idle")
            return
    except Exception:
        logger.warning("Failed to ensure agent running for session %s", session_id, exc_info=True)

    # Fetch user credentials from Vault for sandbox injection
    credentials: dict[str, str] = {}
    if user_external_id:
        credentials = await _fetch_user_credentials(user_external_id)

    full_response = ""
    blocks_meta: list[dict] = []  # Ordered blocks (thinking + text + tool_call) for UI replay
    current_thinking = ""  # Accumulates thinking chunks
    current_text = ""  # Accumulates text chunks between tool calls
    tool_results: dict[str, dict] = {}  # tool_use_id → {content, is_error}

    try:
        stream_url = agent_supervisor.get_stream_url(agent_id, session_id)

        if not stream_url:
            placeholder = "[Agent not running — runtime container needed for inference.]"
            chunk_event = {"type": "chunk", "content": placeholder}
            await redis_service.append_stream_chunk(session_id, chunk_event)
            await redis_service.publish_message(session_id, chunk_event)
            full_response = placeholder
        else:
            # Stream via Supervisor's SSE proxy
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    stream_url,
                    json={
                        "content": content,
                        "session_id": session_id,
                        "model_config_data": agent_model_config,
                        "agent_config": {
                            "instruction": agent_instruction,
                            "tools": agent_tools,
                            "mcp_servers": _build_mcp_config(
                                agent_id, user_token, agent_mcp_servers
                            ),
                            "policy": agent_policy,
                            "user_token": user_token,
                            **({"credentials": credentials} if credentials else {}),
                        },
                    },
                    timeout=300,
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        chunk_data = json.loads(line[6:])

                        chunk_type = chunk_data.get("type")

                        if chunk_type == "chunk":
                            # Flush thinking into blocks on first text chunk
                            if current_thinking:
                                blocks_meta.append({"type": "thinking", "content": current_thinking})
                                current_thinking = ""
                            chunk_text = chunk_data["content"]
                            full_response += chunk_text
                            current_text += chunk_text
                            chunk_event = {"type": "chunk", "content": chunk_text}
                            await redis_service.append_stream_chunk(session_id, chunk_event)
                            await redis_service.publish_message(session_id, chunk_event)
                        elif chunk_type == "tool_use":
                            # Flush accumulated thinking and text before the tool call
                            if current_thinking:
                                blocks_meta.append({"type": "thinking", "content": current_thinking})
                                current_thinking = ""
                            if current_text:
                                blocks_meta.append({"type": "text", "content": current_text})
                                current_text = ""
                            tool_block: dict = {
                                "type": "tool_call",
                                "name": chunk_data.get("name"),
                                "input": chunk_data.get("input"),
                                "tool_use_id": chunk_data.get("tool_use_id"),
                            }
                            if chunk_data.get("parent_tool_use_id"):
                                tool_block["parent_tool_use_id"] = chunk_data["parent_tool_use_id"]
                            blocks_meta.append(tool_block)
                            await redis_service.append_stream_chunk(session_id, chunk_data)
                            await redis_service.publish_message(session_id, chunk_data)
                        elif chunk_type == "tool_result":
                            # Store result to attach to the matching tool_call block
                            tid = chunk_data.get("tool_use_id")
                            result_content = chunk_data.get("content", "")
                            if isinstance(result_content, str) and len(result_content) > 10240:
                                result_content = result_content[:10240] + "\n... (truncated)"
                            if tid:
                                tool_results[tid] = {
                                    "content": result_content,
                                    "is_error": chunk_data.get("is_error", False),
                                }
                            result_data = {**chunk_data, "content": result_content}
                            await redis_service.append_stream_chunk(session_id, result_data)
                            await redis_service.publish_message(session_id, result_data)
                        elif chunk_type == "tool_progress":
                            # Ephemeral — publish for live clients, don't buffer
                            await redis_service.publish_message(session_id, chunk_data)
                        elif chunk_type == "thinking":
                            # Thinking content — buffer + publish so it appears
                            # in replay and is saved into message metadata.
                            thinking_text = chunk_data.get("content", "")
                            current_thinking += thinking_text
                            await redis_service.append_stream_chunk(session_id, chunk_data)
                            await redis_service.publish_message(session_id, chunk_data)

        # Flush remaining thinking and text, then attach tool results to blocks
        if current_thinking:
            blocks_meta.append({"type": "thinking", "content": current_thinking})
        if current_text:
            blocks_meta.append({"type": "text", "content": current_text})
        for block in blocks_meta:
            if block.get("type") == "tool_call" and block.get("tool_use_id") in tool_results:
                tr = tool_results[block["tool_use_id"]]
                block["result"] = tr["content"]
                if tr.get("is_error"):
                    block["is_error"] = True

        # Save completed response to DB (with ordered blocks for UI replay)
        meta = {"blocks": blocks_meta} if blocks_meta else None
        async with async_session_factory() as db:
            msg = await session_service.save_message(
                db, session_uuid, "agent", full_response, metadata=meta
            )
            await db.commit()
            message_id = str(msg.id)

        await redis_service.set_stream_status(session_id, "complete")
        await redis_service.set_stream_result(session_id, full_response, message_id)
        await redis_service.set_session_status(session_id, "idle")

        # Increment unread for ALL participants first, then publish done.
        # Connected clients clear their own unread when they receive the done
        # event via WS relay — this ensures multi-tab scenarios work correctly
        # (same user online in one tab, viewing sidebar in another).
        async with async_session_factory() as db:
            result = await db.execute(
                select(SessionParticipant.user_id).where(
                    SessionParticipant.session_id == session_uuid
                )
            )
            all_participants = {str(row[0]) for row in result.all()}

        for uid in all_participants:
            await redis_service.increment_unread(session_id, uid)

        done_event = {"type": "done", "messageId": message_id}
        await redis_service.publish_message(session_id, done_event)

    except asyncio.CancelledError:
        logger.info("Stream cancelled for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")
    except Exception:
        logger.exception("Stream failed for session %s", session_id)
        await redis_service.set_stream_status(session_id, "error")
        await redis_service.set_session_status(session_id, "idle")

        error_event = {"type": "error", "message": "Agent streaming failed"}
        await redis_service.publish_message(session_id, error_event)

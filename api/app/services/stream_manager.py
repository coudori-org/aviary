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


def _rebuild_blocks_from_chunks(chunks: list[dict]) -> tuple[str, list[dict]]:
    """Reconstruct full_response text and blocks_meta from buffered Redis chunks.

    Used by cancel_stream to save partial progress on abort.
    """
    full_text = ""
    blocks: list[dict] = []
    current_thinking = ""
    current_text = ""
    tool_results: dict[str, dict] = {}

    for chunk in chunks:
        ct = chunk.get("type")
        if ct == "chunk":
            current_text += chunk.get("content", "")
            full_text += chunk.get("content", "")
        elif ct == "thinking":
            current_thinking += chunk.get("content", "")
        elif ct == "tool_use":
            if current_thinking:
                blocks.append({"type": "thinking", "content": current_thinking})
                current_thinking = ""
            if current_text:
                blocks.append({"type": "text", "content": current_text})
                current_text = ""
            tool_block: dict = {
                "type": "tool_call",
                "name": chunk.get("name"),
                "input": chunk.get("input"),
                "tool_use_id": chunk.get("tool_use_id"),
            }
            if chunk.get("parent_tool_use_id"):
                tool_block["parent_tool_use_id"] = chunk["parent_tool_use_id"]
            blocks.append(tool_block)
        elif ct == "tool_result":
            tid = chunk.get("tool_use_id")
            result_content = chunk.get("content", "")
            if isinstance(result_content, str) and len(result_content) > 10240:
                result_content = result_content[:10240] + "\n... (truncated)"
            if tid:
                tool_results[tid] = {
                    "content": result_content,
                    "is_error": chunk.get("is_error", False),
                }

    if current_thinking:
        blocks.append({"type": "thinking", "content": current_thinking})
    if current_text:
        blocks.append({"type": "text", "content": current_text})

    for block in blocks:
        if block.get("type") == "tool_call" and block.get("tool_use_id") in tool_results:
            tr = tool_results[block["tool_use_id"]]
            block["result"] = tr["content"]
            if tr.get("is_error"):
                block["is_error"] = True

    return full_text, blocks


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
    accessible_agents: list[dict] | None = None,
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
            accessible_agents=accessible_agents,
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

    # 3. Save partial response (with blocks + A2A sub-agent events)
    message_id: str | None = None
    try:
        partial = await redis_service.get_stream_chunks(session_id)
        if partial:
            partial_text, blocks_meta = _rebuild_blocks_from_chunks(partial)

            # Fetch sub-agent events for any A2A tool calls
            for block in list(blocks_meta):
                if (
                    block.get("type") == "tool_call"
                    and block.get("name", "").startswith("mcp__a2a__ask_")
                ):
                    tool_use_id = block.get("tool_use_id")
                    if tool_use_id:
                        events = await redis_service.get_a2a_events(
                            session_id, tool_use_id
                        )
                        a2a_results: dict[str, dict] = {}
                        for evt in events:
                            if evt.get("type") == "tool_use":
                                blocks_meta.append({
                                    "type": "tool_call",
                                    "name": evt.get("name"),
                                    "input": evt.get("input", {}),
                                    "tool_use_id": evt.get("tool_use_id"),
                                    "parent_tool_use_id": evt.get("parent_tool_use_id"),
                                })
                            elif evt.get("type") == "tool_result":
                                tid = evt.get("tool_use_id")
                                if tid:
                                    a2a_results[tid] = {
                                        "content": evt.get("content", ""),
                                        "is_error": evt.get("is_error", False),
                                    }
                        for b in blocks_meta:
                            tid = b.get("tool_use_id")
                            if tid and tid in a2a_results:
                                b["result"] = a2a_results[tid]["content"]
                                if a2a_results[tid].get("is_error"):
                                    b["is_error"] = True
                        await redis_service.clear_a2a_events(session_id, tool_use_id)

            meta = {"blocks": blocks_meta} if blocks_meta else None
            async with async_session_factory() as db:
                msg = await session_service.save_message(
                    db, uuid.UUID(session_id), "agent",
                    partial_text or "[Cancelled]", metadata=meta,
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
    accessible_agents: list[dict] | None = None,
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
                            "user_external_id": user_external_id,
                            **({"credentials": credentials} if credentials else {}),
                            **({"accessible_agents": accessible_agents} if accessible_agents else {}),
                        },
                    },
                    timeout=None,
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

        # Fetch sub-agent tool_use/tool_result events for A2A tool calls.
        # Normalize SSE format to blocks_meta format, then merge results
        # into their matching tool_call blocks.
        a2a_extra_blocks: list[dict] = []
        a2a_results: dict[str, dict] = {}  # tool_use_id → {content, is_error}
        for block in blocks_meta:
            if (
                block.get("type") == "tool_call"
                and block.get("name", "").startswith("mcp__a2a__ask_")
            ):
                tool_use_id = block.get("tool_use_id")
                if tool_use_id:
                    events = await redis_service.get_a2a_events(session_id, tool_use_id)
                    for evt in events:
                        if evt.get("type") == "tool_use":
                            a2a_extra_blocks.append({
                                "type": "tool_call",
                                "name": evt.get("name"),
                                "input": evt.get("input", {}),
                                "tool_use_id": evt.get("tool_use_id"),
                                "parent_tool_use_id": evt.get("parent_tool_use_id"),
                            })
                        elif evt.get("type") == "tool_result":
                            tid = evt.get("tool_use_id")
                            if tid:
                                a2a_results[tid] = {
                                    "content": evt.get("content", ""),
                                    "is_error": evt.get("is_error", False),
                                }
                    await redis_service.clear_a2a_events(session_id, tool_use_id)
        if a2a_extra_blocks:
            blocks_meta.extend(a2a_extra_blocks)
            # Attach results to the sub-agent tool_call blocks
            for block in a2a_extra_blocks:
                tid = block.get("tool_use_id")
                if tid and tid in a2a_results:
                    tr = a2a_results[tid]
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

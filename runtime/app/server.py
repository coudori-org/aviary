"""Agent Runtime HTTP server — multi-session server that processes messages via Claude Agent SDK.

Each session is isolated in its own workspace directory (/workspace/sessions/{session_id}/)
and serialized via per-session asyncio locks to prevent concurrent SDK calls.
Filesystem isolation enforced by bubblewrap sandbox (see scripts/claude-sandbox.sh).
"""

import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.health import router as health_router, set_manager, set_ready
from app.session_manager import SessionManager, SessionState, WORKSPACE_ROOT


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    manager = SessionManager()
    app.state.manager = manager
    set_manager(manager)
    set_ready(True)
    yield
    # Shutdown
    set_ready(False)
    await manager.graceful_shutdown(timeout=30)


app = FastAPI(title="Aviary Runtime", version="0.2.0", lifespan=lifespan)
app.include_router(health_router)


class MessageRequest(BaseModel):
    content: str
    session_id: str
    model_config_data: dict | None = None
    agent_config: dict | None = None


@app.post("/message")
async def handle_message(body: MessageRequest):
    """Process a message and return SSE stream."""
    from app.agent import process_message

    manager: SessionManager = app.state.manager

    try:
        entry = await manager.get_or_create(body.session_id)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)

    async def event_stream():
        async with entry._lock:  # serialize messages within this session
            entry.state = SessionState.STREAMING
            entry.last_active_at = time.time()
            try:
                async for chunk in process_message(
                    body.session_id, body.content,
                    body.model_config_data, body.agent_config,
                ):
                    yield f"data: {json.dumps(chunk)}\n\n"
            finally:
                entry.state = SessionState.IDLE

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions")
async def list_sessions():
    """List active sessions on this Pod with capacity info."""
    manager: SessionManager = app.state.manager
    return {
        "sessions": manager.list_sessions(),
        "capacity": manager._max_sessions,
        "active": manager.active_count,
        "streaming": manager.streaming_count,
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Clean up a session's workspace on this Pod."""
    manager: SessionManager = app.state.manager
    removed = await manager.remove(session_id, cleanup_files=True)
    if not removed:
        return JSONResponse({"error": "session not found"}, status_code=404)
    return {"status": "removed"}


@app.get("/metrics")
async def metrics():
    """Return session metrics for scaling decisions."""
    manager: SessionManager = app.state.manager
    return {
        "sessions_active": manager.active_count,
        "sessions_streaming": manager.streaming_count,
        "sessions_max": manager._max_sessions,
    }


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown endpoint."""
    manager: SessionManager = app.state.manager
    set_ready(False)
    return {
        "status": "shutting_down",
        "streaming_sessions": manager.streaming_count,
    }

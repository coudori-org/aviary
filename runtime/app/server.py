"""Agent Runtime HTTP server — receives messages from API Server, processes via Claude Agent SDK."""

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.health import router as health_router, set_ready
from app.history import ensure_history_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    ensure_history_dir()
    set_ready(True)
    yield
    # Shutdown
    set_ready(False)


app = FastAPI(title="Aviary Runtime", version="0.1.0", lifespan=lifespan)
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

    async def event_stream():
        async for chunk in process_message(
            body.content, body.model_config_data, body.agent_config
        ):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown endpoint."""
    set_ready(False)
    return {"status": "shutting_down"}

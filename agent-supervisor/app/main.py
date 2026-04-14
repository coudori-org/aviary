"""Agent Supervisor — activator + SSE proxy + Redis publisher.

Scaling (1→N, N→0) is owned by KEDA. The supervisor only activates idle
agents (0→1) on demand, consumes runtime SSE, and publishes events to
Redis (for WS broadcast + replay buffer) so the API stays off the SSE path.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.backends import get_backend
from app.config import settings
from app import redis_client
from app.routers import agents, deployments

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.init_redis()
    try:
        yield
    finally:
        await redis_client.close_redis()


app = FastAPI(title="Aviary Agent Supervisor", version="0.3.0", lifespan=lifespan)

app.include_router(agents.router, prefix="/v1", tags=["agents"])
app.include_router(deployments.router, prefix="/v1", tags=["admin"])


@app.get("/v1/health")
async def health():
    backend = get_backend()
    ok = await backend.health()
    return {
        "status": "ok" if ok else "degraded",
        "backend": settings.backend_kind,
    }

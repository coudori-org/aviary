"""Agent Supervisor — activator + SSE proxy.

Scaling (1→N, N→0) is owned by KEDA. The supervisor only activates idle
agents (0→1) on demand, proxies SSE, and exposes admin ops via the backend.
"""

import logging

from fastapi import FastAPI

from app.backends import get_backend
from app.config import settings
from app.routers import agents, deployments

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Aviary Agent Supervisor", version="0.2.0")

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

"""Aviary Agent Controller — K8s gateway + infrastructure manager.

Runs inside the K8s platform namespace. Manages agent runtime resources:
- K8s namespace/deployment/service/PVC lifecycle
- Auto-scaling based on session load
- Idle cleanup (scale to zero after inactivity)
- Activity tracking via DB (last_activity_at)
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import agents, deployments, egress, namespaces, streaming
from app import scaling

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scaling_task = asyncio.create_task(scaling.scaling_loop())
    cleanup_task = asyncio.create_task(scaling.idle_cleanup_loop())

    yield

    scaling_task.cancel()
    cleanup_task.cancel()
    try:
        await scaling_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Aviary Agent Controller", version="0.1.0", lifespan=lifespan)

app.include_router(agents.router, prefix="/v1", tags=["agents"])
app.include_router(namespaces.router, prefix="/v1", tags=["namespaces"])
app.include_router(deployments.router, prefix="/v1", tags=["deployments"])
app.include_router(streaming.router, prefix="/v1", tags=["streaming"])
app.include_router(egress.router, prefix="/v1", tags=["egress"])


@app.get("/v1/health")
async def health():
    """Health check — verifies K8s API connectivity."""
    from app.k8s import k8s_apply

    k8s_ok = False
    try:
        await k8s_apply("GET", "/api/v1/namespaces/platform")
        k8s_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if k8s_ok else "degraded",
        "k8s": "connected" if k8s_ok else "unavailable",
    }

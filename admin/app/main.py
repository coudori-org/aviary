"""Aviary Admin Console — platform management service.

No authentication. Local access only.
Manages agent infrastructure: deployments, policies, scaling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agents, deployments, pages, policies
from app.services import controller_client, redis_service, scaling_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def _idle_agent_cleanup_loop():
    """Background task: scale down idle agent deployments every 5 minutes."""
    while True:
        await asyncio.sleep(300)
        try:
            cleaned = await scaling_service.cleanup_idle_agents()
            if cleaned:
                logger.info("Scaled down %d idle agent deployments", cleaned)
        except Exception:
            logger.warning("Idle agent cleanup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_service.init_redis()
    await controller_client.init_client()

    scaling_task = asyncio.create_task(scaling_service.scaling_loop())
    cleanup_task = asyncio.create_task(_idle_agent_cleanup_loop())

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
    await controller_client.close_client()
    await redis_service.close_redis()


app = FastAPI(
    title="Aviary Admin Console",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(deployments.router, prefix="/api/agents", tags=["deployments"])
app.include_router(policies.router, prefix="/api/agents", tags=["policies"])
app.include_router(pages.router, tags=["pages"])


@app.get("/health")
async def health():
    redis_ok = False
    client = redis_service.get_client()
    if client:
        try:
            redis_ok = await client.ping()
        except Exception:
            pass

    return {
        "status": "ok",
        "redis": "connected" if redis_ok else "unavailable",
    }

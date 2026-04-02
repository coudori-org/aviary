"""Aviary Admin Console — platform management service.

No authentication. Local access only.
Edits and applies agent infrastructure configuration: policies, deployments.
Scaling and idle cleanup are handled by the agent controller.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agents, deployments, pages, policies
from app.services import controller_client, redis_service

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_service.init_redis()
    await controller_client.init_client()
    yield
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

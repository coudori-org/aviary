"""Aviary Agent Supervisor — stateless Reverse SSE Proxy.

Each publish request carries its own `runtime_endpoint` (null → supervisor
default). The supervisor consumes SSE from the runtime, publishes events to
Redis, assembles the final response, and returns it — no DB, no K8s API.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app import redis_client
from app.config import settings
from app.routers import agents

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await redis_client.init_redis()
    try:
        yield
    finally:
        await redis_client.close_redis()


app = FastAPI(title="Aviary Agent Supervisor", version="0.4.0", lifespan=lifespan)
app.include_router(agents.router, prefix="/v1", tags=["sessions"])


@app.get("/v1/health")
async def health():
    return {"status": "ok"}


if settings.metrics_enabled:
    @app.get("/metrics")
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

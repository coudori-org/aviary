import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.oidc import init_oidc
from app.config import settings
from app.routers import (
    agent_autocomplete,
    agents,
    auth,
    catalog,
    inference,
    mcp,
    search,
    sessions,
    uploads,
    workflows,
)
from app.services import agent_supervisor, temporal_client
from app.services.redis_service import close_redis, get_client, init_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_oidc()
    await init_redis()
    await agent_supervisor.init_client()
    await temporal_client.init_client()

    yield

    # Shutdown
    await temporal_client.close_client()
    await agent_supervisor.close_client()
    await close_redis()


app = FastAPI(
    title="Aviary API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(
    agent_autocomplete.router, prefix="/api/agents/autocomplete", tags=["agents"]
)
app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(inference.router, prefix="/api/inference", tags=["inference"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["uploads"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])


@app.get("/api/health")
async def health():
    redis_ok = False
    client = get_client()
    if client:
        try:
            redis_ok = await client.ping()
        except Exception:
            logger.warning("Redis ping failed during health check", exc_info=True)

    supervisor_ok = await agent_supervisor.health_check()

    return {
        "status": "ok",
        "redis": "connected" if redis_ok else "unavailable",
        "agent_supervisor": "connected" if supervisor_ok else "unavailable",
    }

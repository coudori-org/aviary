import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.oidc import init_oidc
from app.config import settings
from app.routers import acl, agents, auth, catalog, credentials, inference, sessions
from app.services.redis_service import close_redis, get_client, init_redis

logger = logging.getLogger(__name__)


async def _idle_agent_cleanup_loop():
    """Background task: scale down idle agent Deployments every 5 minutes."""
    from app.db.session import async_session_factory
    from app.services.session_service import cleanup_idle_agents

    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            async with async_session_factory() as db:
                cleaned = await cleanup_idle_agents(db)
                await db.commit()
                if cleaned:
                    logger.info("Scaled down %d idle agent deployments", cleaned)
        except Exception:
            logger.warning("Idle agent cleanup failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_oidc()
    await init_redis()
    cleanup_task = asyncio.create_task(_idle_agent_cleanup_loop())

    # Auto-scaling loop
    from app.services import scaling_service
    scaling_task = asyncio.create_task(scaling_service.scaling_loop())

    yield

    # Shutdown
    cleanup_task.cancel()
    scaling_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await scaling_task
    except asyncio.CancelledError:
        pass
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
app.include_router(acl.router, prefix="/api/agents", tags=["acl"])
app.include_router(catalog.router, prefix="/api/catalog", tags=["catalog"])
app.include_router(credentials.router, prefix="/api/agents", tags=["credentials"])
app.include_router(inference.router, prefix="/api/inference", tags=["inference"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])


@app.get("/api/health")
async def health():
    redis_ok = False
    client = get_client()
    if client:
        try:
            redis_ok = await client.ping()
        except Exception:
            pass
    return {"status": "ok", "redis": "connected" if redis_ok else "unavailable"}

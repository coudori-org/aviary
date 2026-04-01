import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.oidc import init_oidc
from app.config import settings
from app.routers import acl, agents, auth, catalog, credentials, inference, sessions
from app.services import controller_client
from app.services.redis_service import close_redis, get_client, init_redis

logger = logging.getLogger(__name__)


async def _reconcile_deployment_state():
    """Startup task: reset deployment_active for agents whose K8s Deployment is gone.

    After a K8s reset or volume wipe, the DB may still have deployment_active=True
    for agents whose Deployments no longer exist. This causes the system to skip
    re-creation. Resetting the flag ensures ensure_agent_deployment() will
    recreate resources on next message.
    """
    from app.db.session import async_session_factory
    from app.db.models import Agent
    from sqlalchemy import select

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Agent).where(Agent.deployment_active == True, Agent.status != "deleted")
            )
            active_agents = list(result.scalars().all())
            if not active_agents:
                return

            reset_count = 0
            for agent in active_agents:
                if not agent.namespace:
                    continue
                try:
                    status = await controller_client.get_deployment_status(agent.namespace)
                    if status.get("replicas", 0) == 0 and status.get("ready_replicas", 0) == 0:
                        agent.deployment_active = False
                        reset_count += 1
                except Exception:
                    agent.deployment_active = False
                    reset_count += 1

            if reset_count:
                await db.commit()
                logger.info("Reconciled %d stale deployment_active flags (%d agents checked)", reset_count, len(active_agents))
    except Exception:
        logger.warning("Deployment state reconciliation failed (Controller may not be ready yet)", exc_info=True)


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
    await controller_client.init_client()

    cleanup_task = asyncio.create_task(_idle_agent_cleanup_loop())

    # Reconcile stale deployment states
    await _reconcile_deployment_state()

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
    await controller_client.close_client()
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

    controller_ok = False
    try:
        cc = controller_client._client
        if cc:
            resp = await cc.get("/v1/health")
            controller_ok = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "ok",
        "redis": "connected" if redis_ok else "unavailable",
        "controller": "connected" if controller_ok else "unavailable",
    }

"""Aviary Admin Console — platform management service.

No authentication. Local access only.
Edits and applies agent infrastructure configuration: policies, deployments.
Scaling and idle cleanup are handled by the agent supervisor.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agents, deployments, mcp, pages, policies, service_accounts, users, workflows
from app.services import supervisor_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await supervisor_client.init_client()
    yield
    await supervisor_client.close_client()


app = FastAPI(
    title="Aviary Admin Console",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(deployments.router, prefix="/api/agents", tags=["deployments"])
app.include_router(policies.router, prefix="/api/agents", tags=["policies"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(service_accounts.router, prefix="/api/service-accounts", tags=["service-accounts"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(pages.router, tags=["pages"])


@app.get("/health")
async def health():
    return {"status": "ok"}

"""Aviary Admin Console — platform management service.

No authentication. Local access only.
Manages agent config, MCP, users, and workflows. Runtime infrastructure
(environments) is pre-provisioned via Helm/GitOps — the admin console never
touches K8s or per-agent deployments.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import agents, mcp, pages, users, workflows

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


app = FastAPI(
    title="Aviary Admin Console",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(agents.router, prefix="/api/agents", tags=["agents"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(pages.router, tags=["pages"])


@app.get("/health")
async def health():
    return {"status": "ok"}

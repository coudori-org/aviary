"""Aviary Agent Controller — K8s gateway service.

Runs inside the K8s platform namespace. Accepts HTTP requests from the
API server and translates them to K8s API calls using in-cluster
ServiceAccount authentication. No database access, no business logic.
"""

import logging

from fastapi import FastAPI

from app.routers import deployments, egress, namespaces, streaming

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Aviary Agent Controller", version="0.1.0")

app.include_router(namespaces.router, prefix="/v1", tags=["namespaces"])
app.include_router(deployments.router, prefix="/v1", tags=["deployments"])
app.include_router(streaming.router, prefix="/v1", tags=["streaming"])
app.include_router(egress.router, prefix="/v1", tags=["egress"])


@app.get("/v1/health")
async def health():
    """Health check — also verifies K8s API connectivity."""
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

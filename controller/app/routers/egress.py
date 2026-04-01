"""Egress proxy cache invalidation relay."""

import logging

from fastapi import APIRouter

from app.k8s import k8s_apply

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/egress/invalidate/{agent_id}")
async def invalidate_egress_cache(agent_id: str):
    """Relay cache invalidation to the egress-proxy admin API.

    Non-critical — cache has a 30s TTL as fallback.
    """
    try:
        await k8s_apply(
            "POST",
            f"/api/v1/namespaces/platform/services/egress-proxy:8081/proxy/invalidate/{agent_id}",
        )
        return {"ok": True}
    except Exception:
        logger.debug(
            "Egress proxy cache invalidation failed for agent %s (non-critical)", agent_id
        )
        return {"ok": False, "reason": "egress-proxy unreachable"}

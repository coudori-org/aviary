"""Inference backend endpoints — proxied through LiteLLM.

All provider access goes through the LiteLLM gateway.
This ensures a single enforcement point for RBAC, key management, and quotas.
The API server never calls LLM providers directly.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db.models import User

router = APIRouter()

# LiteLLM model name prefix → Aviary backend name
_PREFIX_TO_BACKEND = {
    "anthropic": "claude",
    "ollama": "ollama",
    "vllm": "vllm",
    "bedrock": "bedrock",
}
_BACKEND_TO_PREFIX = {v: f"{k}/" for k, v in _PREFIX_TO_BACKEND.items()}

_AUTH_HEADERS = {"Authorization": f"Bearer {settings.litellm_api_key}"}


async def _fetch_model_info() -> list[dict]:
    """Fetch model info from LiteLLM."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.litellm_url}/model/info",
            headers=_AUTH_HEADERS,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])


@router.get("/models")
async def list_models(user: User = Depends(get_current_user)):
    """List all available models across all backends.

    Each item includes the backend name and full model_info dict from LiteLLM
    so that clients can derive capabilities, token limits, etc. in a single call.
    """
    raw = await _fetch_model_info()
    models = []
    for m in raw:
        name = m.get("model_name", "")
        prefix = name.split("/")[0] if "/" in name else ""
        backend = _PREFIX_TO_BACKEND.get(prefix)
        if backend:
            models.append({
                "id": name,
                "name": name,
                "backend": backend,
                "model_info": m.get("model_info", {}),
            })
    return {"models": models}


@router.get("/{backend}/health")
async def check_backend_health(backend: str, user: User = Depends(get_current_user)):
    """Check LiteLLM gateway health."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.litellm_url}/health/liveliness")
            return {"status": "ok" if resp.status_code == 200 else "error"}
    except httpx.HTTPError as e:  # Best-effort: health check probes LiteLLM connectivity
        return {"status": "error", "error": str(e)}

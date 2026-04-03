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
    "hosted_vllm": "vllm",
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


@router.get("/backends")
async def list_backends(user: User = Depends(get_current_user)):
    """List available inference backends (derived from LiteLLM model list)."""
    models = await _fetch_model_info()
    backends = set()
    for m in models:
        name = m.get("model_name", "")
        prefix = name.split("/")[0] if "/" in name else ""
        if prefix in _PREFIX_TO_BACKEND:
            backends.add(_PREFIX_TO_BACKEND[prefix])
    return {"backends": sorted(backends)}


@router.get("/{backend}/models")
async def list_models(backend: str, user: User = Depends(get_current_user)):
    """List available models for a backend (filtered from LiteLLM model list)."""
    prefix = _BACKEND_TO_PREFIX.get(backend)
    if not prefix:
        raise HTTPException(status_code=400, detail=f"Unknown backend: {backend}")
    models = await _fetch_model_info()
    return {
        "models": [
            {"id": m["model_name"], "name": m["model_name"]}
            for m in models
            if m.get("model_name", "").startswith(prefix)
        ]
    }


@router.get("/{backend}/model-info")
async def get_model_info(
    backend: str, model: str, user: User = Depends(get_current_user)
):
    """Get model metadata from LiteLLM."""
    models = await _fetch_model_info()
    for m in models:
        if m.get("model_name") == model:
            info = m.get("model_info", {})
            return {
                "model": model,
                "backend": backend,
                "defaults": {},
                "limits": {
                    "max_context_length": info.get("max_input_tokens"),
                },
                "capabilities": [],
            }
    raise HTTPException(status_code=404, detail=f"Model not found: {model}")


@router.get("/{backend}/health")
async def check_backend_health(backend: str, user: User = Depends(get_current_user)):
    """Check LiteLLM gateway health."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.litellm_url}/health/liveliness")
            return {"status": "ok" if resp.status_code == 200 else "error"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

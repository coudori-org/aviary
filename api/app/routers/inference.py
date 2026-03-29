"""Inference backend endpoints — list backends, models, and check health."""

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db.models import User

router = APIRouter()

CLAUDE_MODELS = [
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
]


@router.get("/backends")
async def list_backends(user: User = Depends(get_current_user)):
    """List available inference backends and their status."""
    backends = [
        {"name": "claude", "label": "Claude API", "url": "https://api.anthropic.com"},
        {"name": "ollama", "label": "Ollama (Local)", "url": settings.inference_ollama_url},
        {"name": "vllm", "label": "vLLM (Local)", "url": settings.inference_vllm_url},
    ]
    return {"backends": backends}


@router.get("/{backend}/models")
async def list_models(backend: str, user: User = Depends(get_current_user)):
    """List available models for a backend."""
    if backend == "claude":
        return {"models": [{"id": m, "name": m} for m in CLAUDE_MODELS]}

    if backend == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.inference_ollama_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                models = [
                    {"id": m["name"], "name": m["name"], "size": m.get("size")}
                    for m in data.get("models", [])
                ]
                return {"models": models}
        except Exception:
            return {"models": [], "error": "Ollama not reachable"}

    if backend == "vllm":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.inference_vllm_url}/v1/models")
                resp.raise_for_status()
                data = resp.json()
                models = [
                    {"id": m["id"], "name": m["id"]}
                    for m in data.get("data", [])
                ]
                return {"models": models}
        except Exception:
            return {"models": [], "error": "vLLM not reachable"}

    raise HTTPException(status_code=404, detail=f"Unknown backend: {backend}")


@router.post("/{backend}/health")
async def check_backend_health(backend: str, user: User = Depends(get_current_user)):
    """Check connectivity to an inference backend."""
    if backend == "claude":
        return {"status": "ok", "message": "Claude API is cloud-hosted"}

    url_map = {
        "ollama": settings.inference_ollama_url,
        "vllm": settings.inference_vllm_url,
    }
    base_url = url_map.get(backend)
    if not base_url:
        raise HTTPException(status_code=404, detail=f"Unknown backend: {backend}")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(base_url)
            return {"status": "ok", "http_status": resp.status_code}
    except Exception as e:
        return {"status": "error", "message": str(e)}

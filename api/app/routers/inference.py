"""Inference backend endpoints — proxied through LiteLLM.

All provider access goes through the LiteLLM gateway. This router is a
thin passthrough: we fetch the model catalogue from LiteLLM and report
each entry's prefix as its `backend`, with no translation. Whatever
LiteLLM calls a provider (``anthropic``, ``ollama``, ``vllm``, …) is
what Aviary calls it.
"""

import httpx
from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.config import settings
from app.db.models import User

router = APIRouter()

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
    """List all models LiteLLM reports.

    The `backend` field is simply the prefix before the first ``/`` in
    LiteLLM's ``model_name``. Models without a provider prefix are
    skipped — Aviary requires a qualified name so it can be stored and
    replayed verbatim later.
    """
    raw = await _fetch_model_info()
    models = []
    for m in raw:
        name = m.get("model_name", "")
        if "/" not in name:
            continue
        backend = name.split("/", 1)[0]
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

"""Server-authoritative identity enrichment — overwrites caller-supplied
identity/credential fields on agent_config so the runtime can't be lied to."""

from __future__ import annotations

import logging

from fastapi import HTTPException

from aviary_shared.vault import PLATFORM_NAMESPACE

from app.auth.dependencies import IdentityContext
from app.config import settings
from app.services import llm_backends_resolver
from app.services.vault_client import fetch_user_credential, fetch_user_credentials


logger = logging.getLogger(__name__)


async def _inject_direct_llm(agent_config: dict, sub: str) -> None:
    mc = agent_config.get("model_config") or {}
    backend = mc.get("backend")
    model = mc.get("model")
    if not backend or not model:
        raise HTTPException(
            status_code=400,
            detail="agent_config.model_config.backend and .model are required in direct mode",
        )
    entry = llm_backends_resolver.resolve(backend, model)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model {backend}/{model} in direct-mode config.yaml",
        )
    mc["model"] = entry.model
    if entry.api_base is not None:
        mc["api_base"] = entry.api_base
    else:
        mc.pop("api_base", None)
    # Literal `api_key` in llm_backends wins (e.g. local models pinned to "none");
    # otherwise fall back to per-user secret at aviary/{backend}-api-key.
    api_key = entry.api_key
    if api_key is None:
        api_key = await fetch_user_credential(
            sub, PLATFORM_NAMESPACE, f"{backend}-api-key",
        )
    mc["api_key"] = api_key or ""
    agent_config["model_config"] = mc


async def enrich_agent_config(body: dict, identity: IdentityContext) -> None:
    agent_config = body.get("agent_config") or {}
    if not agent_config.get("agent_id"):
        raise HTTPException(status_code=400, detail="agent_config.agent_id is required")

    agent_config["user_external_id"] = identity.sub
    if identity.user_token:
        agent_config["user_token"] = identity.user_token
    else:
        agent_config.pop("user_token", None)

    credentials = await fetch_user_credentials(identity.sub)
    if credentials:
        agent_config["credentials"] = credentials
    else:
        agent_config.pop("credentials", None)

    if settings.direct_llm_mode:
        await _inject_direct_llm(agent_config, identity.sub)
    else:
        # Caller can't redirect the runtime by smuggling api_base/api_key in the body.
        mc = agent_config.get("model_config")
        if isinstance(mc, dict):
            mc.pop("api_base", None)
            mc.pop("api_key", None)

    body["agent_config"] = agent_config
    body.pop("on_behalf_of_sub", None)

    logger.info(
        "agent_config enriched sub=%s agent_id=%s on_behalf_token=%s credentials=%s",
        identity.sub,
        agent_config.get("agent_id"),
        bool(identity.user_token),
        sorted(credentials.keys()) if credentials else [],
    )

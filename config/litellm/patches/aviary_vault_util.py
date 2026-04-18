"""Vault credential lookup for LiteLLM patches.

NO cache by design — when a user updates a credential in the admin UI
we want the next call to pick it up immediately. The Vault hit per
tool-call is acceptable; if it ever isn't, add caching at a layer that
also exposes invalidation (not here).
"""

from __future__ import annotations

import logging
import os
import time

import httpx


logger = logging.getLogger(__name__)

VAULT_ADDR = os.environ.get("VAULT_ADDR", "")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")

# Slow-Vault threshold. Anything above this indicates the per-call hit is
# becoming a real latency contributor — time to add invalidation-aware caching.
_SLOW_FETCH_SECONDS = 0.5


async def fetch_credential(sub: str, key: str) -> str | None:
    """Return ``secret/aviary/credentials/{sub}/{key}`` or ``None`` if 404.

    Raises ``Exception`` on transport error (so callers can surface a
    "credential service unavailable" 5xx) and on misconfiguration.
    """
    if not VAULT_ADDR or not VAULT_TOKEN:
        raise Exception("Vault not configured (VAULT_ADDR / VAULT_TOKEN)")

    url = f"{VAULT_ADDR}/v1/secret/data/aviary/credentials/{sub}/{key}"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers={"X-Vault-Token": VAULT_TOKEN}, timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("Vault miss sub=%s key=%s", sub, key)
                return None
            resp.raise_for_status()
            return resp.json()["data"]["data"].get("value")
    except httpx.HTTPError as exc:
        raise Exception(f"Vault error fetching '{key}': {exc}") from exc
    finally:
        elapsed = time.monotonic() - started
        if elapsed > _SLOW_FETCH_SECONDS:
            logger.warning(
                "Vault fetch slow key=%s elapsed=%.2fs", key, elapsed,
            )

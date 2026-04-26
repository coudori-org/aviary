"""Per-user credential lookup for LiteLLM patches. Vault primary, config.yaml fallback.

Intentionally uncached — credential updates must take effect on the next call.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import httpx
import yaml


logger = logging.getLogger(__name__)

VAULT_ADDR = os.environ.get("VAULT_ADDR", "")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")

CONFIG_PATH = os.environ.get("AVIARY_CONFIG_PATH", "")

PLATFORM_NAMESPACE = "aviary"

# Warn above this — sustained slow fetches mean we should add invalidation-aware caching.
_SLOW_FETCH_SECONDS = 0.5


def _vault_enabled() -> bool:
    return bool(VAULT_ADDR and VAULT_TOKEN)


def _lookup_config_secret(sub: str, namespace: str, key: str) -> str | None:
    if not CONFIG_PATH:
        return None
    p = Path(CONFIG_PATH)
    if not p.exists():
        return None
    raw = yaml.safe_load(p.read_text()) or {}
    table = raw.get("secrets") or {}
    if not isinstance(table, dict):
        return None
    user = table.get(sub) or {}
    if not isinstance(user, dict):
        return None
    entries = user.get(namespace) or {}
    if not isinstance(entries, dict):
        return None
    value = entries.get(key)
    return str(value) if value is not None else None


async def fetch_credential(sub: str, namespace: str, key: str) -> str | None:
    """Return the credential or ``None`` if missing.

    Raises ``Exception`` on Vault transport error so callers can surface
    a "credential service unavailable" 5xx.
    """
    if not _vault_enabled():
        return _lookup_config_secret(sub, namespace, key)

    url = f"{VAULT_ADDR}/v1/secret/data/aviary/credentials/{sub}/{namespace}/{key}"
    started = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers={"X-Vault-Token": VAULT_TOKEN}, timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("Vault miss sub=%s ns=%s key=%s", sub, namespace, key)
                return None
            resp.raise_for_status()
            return resp.json()["data"]["data"].get("value")
    except httpx.HTTPError as exc:
        raise Exception(f"Vault error fetching '{namespace}/{key}': {exc}") from exc
    finally:
        elapsed = time.monotonic() - started
        if elapsed > _SLOW_FETCH_SECONDS:
            logger.warning(
                "Vault fetch slow ns=%s key=%s elapsed=%.2fs",
                namespace, key, elapsed,
            )

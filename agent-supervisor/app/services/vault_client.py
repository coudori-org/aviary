"""Per-user credential fetcher.

Primary source is Vault. When ``VAULT_ADDR`` / ``VAULT_TOKEN`` are unset
the supervisor falls back to the ``secrets:`` table in config.yaml so a
developer can run the stack without standing up Vault.
"""

import logging
import time
from functools import lru_cache

from aviary_shared.config_secrets import ConfigSecrets, load_secrets
from aviary_shared.vault import PLATFORM_NAMESPACE, VaultClient

from app import metrics
from app.config import settings

logger = logging.getLogger(__name__)

_client: VaultClient | None = None


def _vault() -> VaultClient:
    global _client
    if _client is None:
        _client = VaultClient(settings.vault_addr, settings.vault_token)
    return _client


@lru_cache(maxsize=1)
def _config_secrets() -> ConfigSecrets:
    return load_secrets(settings.llm_backends_config_path)


async def fetch_user_credentials(user_external_id: str) -> dict[str, str]:
    creds: dict[str, str] = {}
    started = time.monotonic()
    try:
        if settings.vault_enabled:
            github_token = await _vault().read_user_credential(
                user_external_id, PLATFORM_NAMESPACE, "github-token",
            )
        else:
            github_token = _config_secrets().lookup(
                user_external_id, PLATFORM_NAMESPACE, "github-token",
            )
    finally:
        metrics.vault_fetch_duration_seconds.record(time.monotonic() - started)
    if github_token:
        creds["github_token"] = github_token
    return creds

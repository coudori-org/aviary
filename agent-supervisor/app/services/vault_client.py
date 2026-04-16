"""Vault client for fetching per-user credentials (GitHub token, etc.)."""

from aviary_shared.vault import VaultClient

from app.config import settings

_client: VaultClient | None = None


def _vault() -> VaultClient:
    global _client
    if _client is None:
        _client = VaultClient(settings.vault_addr, settings.vault_token)
    return _client


async def fetch_user_credentials(user_external_id: str) -> dict[str, str]:
    """Fetch credentials the runtime can inject into the sandbox.

    Currently just the GitHub token. Missing keys are silently skipped so
    users without a given credential still get a working sandbox.
    """
    creds: dict[str, str] = {}
    github_token = await _vault().read_user_credential(user_external_id, "github-token")
    if github_token:
        creds["github_token"] = github_token
    return creds

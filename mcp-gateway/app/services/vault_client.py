"""Vault client for fetching per-user MCP credentials."""

from aviary_shared.vault import VaultClient

from app.config import settings

_client: VaultClient | None = None


def _vault() -> VaultClient:
    global _client
    if _client is None:
        _client = VaultClient(settings.vault_addr, settings.vault_token)
    return _client


async def get_mcp_credential(user_external_id: str, server_name: str) -> str | None:
    return await _vault().read_user_credential(user_external_id, server_name)

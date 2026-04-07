"""Vault client for fetching per-user credentials.

Convention: credentials are stored at
  secret/aviary/credentials/{user_external_id}/{key_name}
with a JSON body {"value": "<secret_string>"}.
"""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def get_mcp_credential(user_external_id: str, server_name: str) -> str | None:
    """Fetch a user's MCP credential from Vault.

    Returns the token string if found, None otherwise.
    """
    if not settings.vault_addr or not settings.vault_token:
        logger.warning("Vault not configured — cannot fetch MCP credentials")
        return None

    vault_path = f"aviary/credentials/{user_external_id}/{server_name}"
    url = f"{settings.vault_addr}/v1/secret/data/{vault_path}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers={"X-Vault-Token": settings.vault_token},
                timeout=10,
            )
            if resp.status_code == 404:
                logger.debug("No credential at %s", vault_path)
                return None
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["data"].get("value")
    except Exception:
        logger.warning("Failed to fetch credential from Vault: %s", vault_path, exc_info=True)
        return None

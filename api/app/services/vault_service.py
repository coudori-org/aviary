"""HashiCorp Vault integration for secret management."""

import httpx

from app.config import settings


async def read_secret(path: str) -> dict:
    """Read a secret from Vault KV v2.

    path: e.g. 'aviary/agents/{agent_id}/credentials/{name}'
    Returns the secret data dict.
    """
    url = f"{settings.vault_addr}/v1/secret/data/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"X-Vault-Token": settings.vault_token},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"]["data"]


async def write_secret(path: str, data: dict) -> None:
    """Write a secret to Vault KV v2."""
    url = f"{settings.vault_addr}/v1/secret/data/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={"X-Vault-Token": settings.vault_token},
            json={"data": data},
            timeout=10,
        )
        resp.raise_for_status()


async def delete_secret(path: str) -> None:
    """Delete a secret from Vault KV v2."""
    url = f"{settings.vault_addr}/v1/secret/data/{path}"
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            url,
            headers={"X-Vault-Token": settings.vault_token},
            timeout=10,
        )
        # 404 = already deleted, not an error
        if resp.status_code != 404:
            resp.raise_for_status()

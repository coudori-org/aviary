"""Vault client for reading secrets."""

import os

import httpx

VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://vault:8200")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "dev-root-token")


async def get_secret(vault_path: str) -> str | None:
    """Read a secret value from Vault. Returns None if not found."""
    url = f"{VAULT_ADDR}/v1/secret/data/{vault_path}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"X-Vault-Token": VAULT_TOKEN},
            timeout=10,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()["data"]["data"]
        return data.get("value")

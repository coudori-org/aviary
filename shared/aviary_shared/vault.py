"""Async Vault KV v2 client.

Per-user credentials live at ``secret/aviary/credentials/{sub}/{key_name}``
where ``sub`` is the OIDC subject claim. Methods return ``None`` for missing
secrets but raise ``httpx.HTTPError`` for transport failures so callers can
tell "no credential" apart from "Vault unreachable".
"""

from __future__ import annotations

import httpx


def credential_path(user_external_id: str, key_name: str) -> str:
    return f"aviary/credentials/{user_external_id}/{key_name}"


class VaultClient:
    def __init__(self, addr: str, token: str, *, timeout: float = 10.0) -> None:
        if not addr or not token:
            raise ValueError("Vault addr and token are required")
        self._addr = addr.rstrip("/")
        self._token = token
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Vault-Token": self._token}

    async def read(self, path: str) -> dict | None:
        url = f"{self._addr}/v1/secret/data/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self._headers, timeout=self._timeout)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()["data"]["data"]

    async def write(self, path: str, data: dict) -> None:
        url = f"{self._addr}/v1/secret/data/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={**self._headers, "Content-Type": "application/json"},
                json={"data": data},
                timeout=self._timeout,
            )
            resp.raise_for_status()

    async def delete(self, path: str) -> None:
        url = f"{self._addr}/v1/secret/metadata/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(url, headers=self._headers, timeout=self._timeout)
            if resp.status_code != 404:
                resp.raise_for_status()

    async def list_keys(self, path: str) -> list[str]:
        url = f"{self._addr}/v1/secret/metadata/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                "LIST", url, headers=self._headers, timeout=self._timeout,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return resp.json().get("data", {}).get("keys", [])

    async def read_user_credential(
        self, user_external_id: str, key_name: str,
    ) -> str | None:
        secret = await self.read(credential_path(user_external_id, key_name))
        if secret is None:
            return None
        return secret.get("value")

    async def write_user_credential(
        self, user_external_id: str, key_name: str, value: str,
    ) -> None:
        await self.write(credential_path(user_external_id, key_name), {"value": value})

    async def delete_user_credential(
        self, user_external_id: str, key_name: str,
    ) -> None:
        await self.delete(credential_path(user_external_id, key_name))

    async def list_user_credentials(self, user_external_id: str) -> list[str]:
        keys = await self.list_keys(f"aviary/credentials/{user_external_id}")
        return [k.rstrip("/") for k in keys]

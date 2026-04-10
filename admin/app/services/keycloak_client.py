"""Keycloak admin API client."""

import logging

import httpx
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


async def get_admin_token() -> str:
    """Obtain an admin access token from Keycloak."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.keycloak_url}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": settings.keycloak_admin,
                "password": settings.keycloak_admin_password,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def create_user(
    email: str, display_name: str, password: str, groups: list[str],
) -> str:
    """Create user in Keycloak and assign groups. Returns keycloak user ID."""
    token = await get_admin_token()
    base = f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    parts = display_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    async with httpx.AsyncClient() as client:
        # Create user
        resp = await client.post(
            f"{base}/users",
            headers=headers,
            json={
                "username": email,
                "email": email,
                "emailVerified": True,
                "enabled": True,
                "firstName": first_name,
                "lastName": last_name,
                "credentials": [{"type": "password", "value": password, "temporary": False}],
            },
            timeout=10,
        )
        if resp.status_code not in (201, 409):
            raise HTTPException(status_code=502, detail=f"Keycloak user creation failed: {resp.text}")

        # Get user ID
        resp = await client.get(
            f"{base}/users?email={email}",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        users = resp.json()
        if not users:
            raise HTTPException(status_code=502, detail="Keycloak user created but not found")
        kc_user_id = users[0]["id"]

        # Assign groups
        for group_name in groups:
            resp = await client.get(
                f"{base}/groups?search={group_name}",
                headers=headers,
                timeout=10,
            )
            kc_groups = resp.json()
            for g in kc_groups:
                if g["name"] == group_name:
                    await client.put(
                        f"{base}/users/{kc_user_id}/groups/{g['id']}",
                        headers=headers,
                        timeout=10,
                    )
                    break

    return kc_user_id


async def list_users() -> list[dict]:
    """Fetch all users from Keycloak. Returns list of Keycloak user dicts."""
    token = await get_admin_token()
    base = f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base}/users?max=500", headers=headers, timeout=10,
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_groups(kc_user_id: str) -> list[str]:
    """Fetch group names for a Keycloak user."""
    token = await get_admin_token()
    base = f"{settings.keycloak_url}/admin/realms/{settings.keycloak_realm}"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base}/users/{kc_user_id}/groups", headers=headers, timeout=10,
        )
        resp.raise_for_status()
        return [g["name"] for g in resp.json()]

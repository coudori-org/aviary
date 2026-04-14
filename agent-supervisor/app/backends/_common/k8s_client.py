"""In-cluster Kubernetes API client shared by K3S and EKS backends."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
_K8S_API = "https://kubernetes.default.svc"


def new_client() -> httpx.AsyncClient:
    token = _TOKEN_PATH.read_text()
    ca_path = str(_CA_PATH) if _CA_PATH.exists() else False
    return httpx.AsyncClient(
        base_url=_K8S_API,
        headers={"Authorization": f"Bearer {token}"},
        verify=ca_path,
        timeout=30,
    )


async def k8s_apply(method: str, path: str, body: dict | None = None) -> dict:
    """K8s request with idempotent 409/404 handling."""
    async with new_client() as client:
        if method == "GET":
            resp = await client.get(path)
        elif method == "POST":
            resp = await client.post(path, json=body)
        elif method == "PUT":
            resp = await client.put(path, json=body)
        elif method == "PATCH":
            resp = await client.patch(
                path,
                content=json.dumps(body),
                headers={"Content-Type": "application/strategic-merge-patch+json"},
            )
        elif method == "DELETE":
            resp = await client.delete(path)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code == 409:
            logger.info("Resource already exists: %s", path)
            return resp.json()
        if resp.status_code == 404 and method == "DELETE":
            return {}

        resp.raise_for_status()
        return resp.json() if resp.content else {}


async def apply_or_replace(path: str, name: str, manifest: dict) -> None:
    """POST; on 409 fall back to PUT to the named resource URL."""
    result = await k8s_apply("POST", path, manifest)
    if result.get("code") == 409 or result.get("reason") == "AlreadyExists":
        await k8s_apply("PUT", f"{path}/{name}", manifest)

"""Kubernetes client using in-cluster ServiceAccount authentication.

Runs inside a K8s Pod in the platform namespace. Auth is automatic
via the mounted ServiceAccount token and CA certificate.
"""

import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# In-cluster auth paths (auto-mounted by K8s)
_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_CA_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
_K8S_API = "https://kubernetes.default.svc"


def _get_k8s_client() -> httpx.AsyncClient:
    """Create an httpx client using in-cluster ServiceAccount auth."""
    token = _TOKEN_PATH.read_text()
    ca_path = str(_CA_PATH) if _CA_PATH.exists() else False

    return httpx.AsyncClient(
        base_url=_K8S_API,
        headers={"Authorization": f"Bearer {token}"},
        verify=ca_path,
        timeout=30,
    )


async def k8s_apply(method: str, path: str, body: dict | None = None) -> dict:
    """Make a K8s API request with idempotent error handling."""
    async with _get_k8s_client() as client:
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
            logger.info("Resource not found for deletion: %s", path)
            return {}

        resp.raise_for_status()
        return resp.json() if resp.content else {}

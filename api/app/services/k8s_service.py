"""Kubernetes operations for agent namespace provisioning.

Creates/deletes: Namespace, ConfigMap, NetworkPolicy, ResourceQuota, ServiceAccount
per agent as defined in CLAUDE.md.
"""

import base64
import json
import logging
import tempfile
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_k8s_base_url: str | None = None
_k8s_headers: dict[str, str] = {}
_k8s_cert: tuple[str, str] | None = None  # (cert_path, key_path) for client certs
_k8s_initialized = False


def _load_kubeconfig() -> None:
    """Load K8s API URL and credentials from kubeconfig file."""
    global _k8s_base_url, _k8s_headers, _k8s_cert, _k8s_initialized
    import yaml

    kubeconfig_path = settings.kubeconfig
    if not kubeconfig_path or not Path(kubeconfig_path).exists():
        logger.warning("kubeconfig not found at %s — K8s operations will be unavailable", kubeconfig_path)
        _k8s_base_url = None
        _k8s_initialized = True
        return

    with open(kubeconfig_path) as f:
        config = yaml.safe_load(f)

    cluster = config["clusters"][0]["cluster"]
    _k8s_base_url = cluster["server"]

    user = config["users"][0]["user"]

    # K8s uses client-certificate-data (base64 PEM in kubeconfig)
    cert_data = user.get("client-certificate-data")
    key_data = user.get("client-key-data")

    if cert_data and key_data:
        # Write decoded PEM to temp files for httpx SSL
        cert_path = Path(tempfile.gettempdir()) / "k8s-client.crt"
        key_path = Path(tempfile.gettempdir()) / "k8s-client.key"
        cert_path.write_bytes(base64.b64decode(cert_data))
        key_path.write_bytes(base64.b64decode(key_data))
        key_path.chmod(0o600)
        _k8s_cert = (str(cert_path), str(key_path))
        logger.info("K8s: using client certificate auth → %s", _k8s_base_url)
    elif user.get("token"):
        _k8s_headers = {"Authorization": f"Bearer {user['token']}"}
        logger.info("K8s: using bearer token auth → %s", _k8s_base_url)
    else:
        logger.warning("K8s: no credentials found in kubeconfig")

    _k8s_initialized = True


def _get_k8s_client() -> httpx.AsyncClient:
    """Create an httpx client configured for K8s API access."""
    if not _k8s_initialized:
        _load_kubeconfig()

    if _k8s_base_url is None:
        raise RuntimeError("K8s is not configured — kubeconfig missing or invalid")

    return httpx.AsyncClient(
        base_url=_k8s_base_url,
        headers=_k8s_headers,
        cert=_k8s_cert,
        verify=False,  # K8s uses self-signed CA
        timeout=30,
    )


async def _k8s_apply(method: str, path: str, body: dict | None = None) -> dict:
    """Make a K8s API request."""
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


_base_egress_rules: list[dict] | None = None


async def _get_base_egress_rules() -> list[dict]:
    """Read base egress rules from the network-policy-base ConfigMap in platform namespace."""
    global _base_egress_rules
    if _base_egress_rules is not None:
        return _base_egress_rules

    data = await _k8s_apply("GET", "/api/v1/namespaces/platform/configmaps/network-policy-base")
    raw = data.get("data", {}).get("rules.json")
    if not raw:
        raise RuntimeError("network-policy-base ConfigMap missing or empty in platform namespace")
    _base_egress_rules = json.loads(raw)
    logger.info("Loaded %d base egress rules from ConfigMap", len(_base_egress_rules))
    return _base_egress_rules


async def _build_egress_rules(policy: dict) -> list[dict]:
    """Build K8s NetworkPolicy egress rules from agent policy.

    Base rules are read from the network-policy-base ConfigMap (platform namespace).
    CIDR-based allowedEgress entries are appended as direct NetworkPolicy rules.
    Domain-based entries are enforced exclusively by the egress-proxy.
    """
    rules = list(await _get_base_egress_rules())

    # Add CIDR-based entries as direct NetworkPolicy rules
    for entry in policy.get("allowedEgress", []):
        cidr = entry.get("cidr")
        if not cidr:
            continue  # domain-based rules are enforced by egress-proxy only
        rule: dict = {"to": [{"ipBlock": {"cidr": cidr}}]}
        if entry.get("ports"):
            rule["ports"] = [
                {"port": p["port"], "protocol": p.get("protocol", "TCP")}
                for p in entry["ports"]
            ]
        rules.append(rule)

    return rules


def _network_policy_manifest(namespace: str, egress_rules: list[dict]) -> dict:
    """Build the full NetworkPolicy manifest."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "session-egress", "namespace": namespace},
        "spec": {
            "podSelector": {"matchLabels": {"aviary/role": "agent-runtime"}},
            "policyTypes": ["Egress", "Ingress"],
            "ingress": [],
            "egress": egress_rules,
        },
    }


async def _apply_network_policy(namespace: str, policy: dict) -> None:
    """Create or replace the session-egress NetworkPolicy for an agent namespace."""
    egress_rules = await _build_egress_rules(policy)
    manifest = _network_policy_manifest(namespace, egress_rules)
    path = f"/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies"
    result = await _k8s_apply("POST", path, manifest)
    # POST returns 409 if already exists — replace with PUT
    if result.get("code") == 409 or result.get("reason") == "AlreadyExists":
        await _k8s_apply("PUT", f"{path}/session-egress", manifest)


async def update_network_policy(namespace: str, policy: dict) -> None:
    """Update the NetworkPolicy for an agent namespace. Changes take effect immediately."""
    await _apply_network_policy(namespace, policy)
    logger.info("Updated NetworkPolicy in namespace %s", namespace)


async def create_agent_namespace(
    agent_id: str,
    owner_id: str,
    instruction: str,
    tools: list,
    policy: dict,
    mcp_servers: list,
) -> str:
    """Provision all K8s resources for a new agent. Returns namespace name."""
    ns_name = f"agent-{agent_id}"

    # 1. Namespace
    await _k8s_apply("POST", "/api/v1/namespaces", {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": ns_name,
            "labels": {
                "aviary/agent-id": agent_id,
                "aviary/owner": owner_id,
                "aviary/managed": "true",
            },
        },
    })

    # 2. ConfigMap
    await _k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/configmaps", {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "agent-config", "namespace": ns_name},
        "data": {
            "instruction.md": instruction,
            "tools.json": json.dumps(tools),
            "policy.json": json.dumps(policy),
            "mcp-servers.json": json.dumps(mcp_servers),
        },
    })

    # 3. NetworkPolicy
    await _apply_network_policy(ns_name, policy)

    # 4. ResourceQuota — based on max_pods for agent-per-pod architecture
    max_pods = policy.get("maxPods", 3)
    await _k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/resourcequotas", {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": "session-quota", "namespace": ns_name},
        "spec": {
            "hard": {
                "pods": str(max_pods + 2),  # +2 headroom for rolling updates
                "requests.cpu": "10",
                "requests.memory": "10Gi",
                "limits.cpu": "20",
                "limits.memory": "20Gi",
                "persistentvolumeclaims": "10",
            },
        },
    })

    # 5. ServiceAccount
    await _k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/serviceaccounts", {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": "session-runner", "namespace": ns_name},
        "automountServiceAccountToken": False,
    })

    logger.info("Created K8s resources for agent %s in namespace %s", agent_id, ns_name)
    return ns_name


async def update_agent_config(
    namespace: str,
    instruction: str,
    tools: list,
    policy: dict,
    mcp_servers: list,
) -> None:
    """Update the agent ConfigMap in K8s."""
    await _k8s_apply("PUT", f"/api/v1/namespaces/{namespace}/configmaps/agent-config", {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "agent-config", "namespace": namespace},
        "data": {
            "instruction.md": instruction,
            "tools.json": json.dumps(tools),
            "policy.json": json.dumps(policy),
            "mcp-servers.json": json.dumps(mcp_servers),
        },
    })


async def delete_agent_namespace(agent_id: str) -> None:
    """Delete the entire agent namespace and all its resources."""
    ns_name = f"agent-{agent_id}"
    await _k8s_apply("DELETE", f"/api/v1/namespaces/{ns_name}")
    logger.info("Deleted namespace %s", ns_name)

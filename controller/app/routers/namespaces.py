"""Namespace lifecycle: create/update/delete agent K8s resources."""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.k8s import k8s_apply

logger = logging.getLogger(__name__)

router = APIRouter()

_base_egress_rules: list[dict] | None = None


async def _get_base_egress_rules() -> list[dict]:
    """Read base egress rules from the network-policy-base ConfigMap in platform namespace."""
    global _base_egress_rules
    if _base_egress_rules is not None:
        return _base_egress_rules

    data = await k8s_apply("GET", "/api/v1/namespaces/platform/configmaps/network-policy-base")
    raw = data.get("data", {}).get("rules.json")
    if not raw:
        raise RuntimeError("network-policy-base ConfigMap missing or empty in platform namespace")
    _base_egress_rules = json.loads(raw)
    logger.info("Loaded %d base egress rules from ConfigMap", len(_base_egress_rules))
    return _base_egress_rules


async def _build_egress_rules(policy: dict) -> list[dict]:
    """Build K8s NetworkPolicy egress rules from agent policy."""
    rules = list(await _get_base_egress_rules())

    for entry in policy.get("allowedEgress", []):
        cidr = entry.get("cidr")
        if not cidr:
            continue
        rule: dict = {"to": [{"ipBlock": {"cidr": cidr}}]}
        if entry.get("ports"):
            rule["ports"] = [
                {"port": p["port"], "protocol": p.get("protocol", "TCP")}
                for p in entry["ports"]
            ]
        rules.append(rule)

    return rules


def _network_policy_manifest(namespace: str, egress_rules: list[dict]) -> dict:
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
    egress_rules = await _build_egress_rules(policy)
    manifest = _network_policy_manifest(namespace, egress_rules)
    path = f"/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies"
    result = await k8s_apply("POST", path, manifest)
    if result.get("code") == 409 or result.get("reason") == "AlreadyExists":
        await k8s_apply("PUT", f"{path}/session-egress", manifest)


class CreateNamespaceRequest(BaseModel):
    agent_id: str
    owner_id: str
    instruction: str
    tools: list
    policy: dict
    mcp_servers: list


@router.post("/namespaces")
async def create_namespace(body: CreateNamespaceRequest):
    """Provision all K8s resources for a new agent."""
    ns_name = f"agent-{body.agent_id}"

    try:
        # 1. Namespace
        await k8s_apply("POST", "/api/v1/namespaces", {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": ns_name,
                "labels": {
                    "aviary/agent-id": body.agent_id,
                    "aviary/owner": body.owner_id,
                    "aviary/managed": "true",
                },
            },
        })

        # 2. ConfigMap
        await k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/configmaps", {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "agent-config", "namespace": ns_name},
            "data": {
                "instruction.md": body.instruction,
                "tools.json": json.dumps(body.tools),
                "policy.json": json.dumps(body.policy),
                "mcp-servers.json": json.dumps(body.mcp_servers),
            },
        })

        # 3. NetworkPolicy
        await _apply_network_policy(ns_name, body.policy)

        # 4. ResourceQuota
        max_pods = body.policy.get("maxPods", 3)
        await k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/resourcequotas", {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {"name": "session-quota", "namespace": ns_name},
            "spec": {
                "hard": {
                    "pods": str(max_pods + 2),
                    "requests.cpu": "10",
                    "requests.memory": "10Gi",
                    "limits.cpu": "20",
                    "limits.memory": "20Gi",
                    "persistentvolumeclaims": "10",
                },
            },
        })

        # 5. ServiceAccount
        await k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/serviceaccounts", {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {"name": "session-runner", "namespace": ns_name},
            "automountServiceAccountToken": False,
        })

        logger.info("Created K8s resources for agent %s in namespace %s", body.agent_id, ns_name)
        return {"namespace": ns_name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class UpdateConfigRequest(BaseModel):
    instruction: str
    tools: list
    policy: dict
    mcp_servers: list


@router.put("/namespaces/{namespace}/config")
async def update_config(namespace: str, body: UpdateConfigRequest):
    """Update the agent ConfigMap in K8s."""
    try:
        await k8s_apply("PUT", f"/api/v1/namespaces/{namespace}/configmaps/agent-config", {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "agent-config", "namespace": namespace},
            "data": {
                "instruction.md": body.instruction,
                "tools.json": json.dumps(body.tools),
                "policy.json": json.dumps(body.policy),
                "mcp-servers.json": json.dumps(body.mcp_servers),
            },
        })
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


class UpdateNetworkPolicyRequest(BaseModel):
    policy: dict


@router.put("/namespaces/{namespace}/network-policy")
async def update_network_policy(namespace: str, body: UpdateNetworkPolicyRequest):
    """Update the NetworkPolicy for an agent namespace."""
    try:
        await _apply_network_policy(namespace, body.policy)
        logger.info("Updated NetworkPolicy in namespace %s", namespace)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/namespaces/{agent_id}")
async def delete_namespace(agent_id: str):
    """Delete the entire agent namespace and all its resources."""
    ns_name = f"agent-{agent_id}"
    try:
        await k8s_apply("DELETE", f"/api/v1/namespaces/{ns_name}")
        logger.info("Deleted namespace %s", ns_name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

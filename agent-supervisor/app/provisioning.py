"""K8s provisioning primitives shared by the agent-centric and K8s-specific routers."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
from fastapi import HTTPException

from aviary_shared.naming import (
    DEPLOYMENT_NAME,
    LABEL_AGENT_ID,
    LABEL_MANAGED,
    LABEL_OWNER,
    LABEL_ROLE,
    NETWORK_POLICY_BASE_CONFIGMAP,
    NETWORK_POLICY_NAME,
    PLATFORM_NAMESPACE,
    PVC_NAME,
    RESOURCE_QUOTA_NAME,
    RUNTIME_PORT,
    SERVICE_ACCOUNT_NAME,
    SERVICE_NAME,
    agent_namespace,
)

from app.config import settings
from app.k8s import k8s_apply
from app.manifests import build_deployment_manifest, build_pvc_manifest, build_service_manifest

logger = logging.getLogger(__name__)


async def _get_base_egress_rules() -> list[dict]:
    """Read the base egress rules ConfigMap on every call (no cache)."""
    try:
        data = await k8s_apply(
            "GET",
            f"/api/v1/namespaces/{PLATFORM_NAMESPACE}/configmaps/{NETWORK_POLICY_BASE_CONFIGMAP}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"{NETWORK_POLICY_BASE_CONFIGMAP} ConfigMap not reachable — platform misconfigured",
        ) from e
    raw = data.get("data", {}).get("rules.json")
    if not raw:
        raise HTTPException(
            status_code=503,
            detail=f"{NETWORK_POLICY_BASE_CONFIGMAP} ConfigMap missing or empty in {PLATFORM_NAMESPACE} namespace",
        )
    return json.loads(raw)


async def _build_egress_rules(policy: dict) -> list[dict]:
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
        "metadata": {"name": NETWORK_POLICY_NAME, "namespace": namespace},
        "spec": {
            "podSelector": {"matchLabels": {LABEL_ROLE: DEPLOYMENT_NAME}},
            "policyTypes": ["Egress", "Ingress"],
            "ingress": [],
            "egress": egress_rules,
        },
    }


async def apply_network_policy(namespace: str, policy: dict) -> None:
    egress_rules = await _build_egress_rules(policy)
    manifest = _network_policy_manifest(namespace, egress_rules)
    path = f"/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies"
    result = await k8s_apply("POST", path, manifest)
    if result.get("code") == 409 or result.get("reason") == "AlreadyExists":
        await k8s_apply("PUT", f"{path}/{NETWORK_POLICY_NAME}", manifest)


async def provision_namespace(agent_id: str, owner_id: str, policy: dict) -> str:
    """Create namespace + NetworkPolicy + ResourceQuota + ServiceAccount. Idempotent."""
    ns_name = agent_namespace(agent_id)

    await k8s_apply("POST", "/api/v1/namespaces", {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": ns_name,
            "labels": {
                LABEL_AGENT_ID: agent_id,
                LABEL_OWNER: owner_id,
                LABEL_MANAGED: "true",
            },
        },
    })

    await apply_network_policy(ns_name, policy)

    max_pods = policy.get("maxPods", 3)
    await k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/resourcequotas", {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": RESOURCE_QUOTA_NAME, "namespace": ns_name},
        "spec": {
            "hard": {
                "pods": str(max_pods + settings.quota_pods_buffer),
                "requests.cpu": settings.quota_requests_cpu,
                "requests.memory": settings.quota_requests_memory,
                "limits.cpu": settings.quota_limits_cpu,
                "limits.memory": settings.quota_limits_memory,
                "persistentvolumeclaims": str(settings.quota_pvcs),
            },
        },
    })

    await k8s_apply("POST", f"/api/v1/namespaces/{ns_name}/serviceaccounts", {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": SERVICE_ACCOUNT_NAME, "namespace": ns_name},
        "automountServiceAccountToken": False,
    })

    logger.info("Provisioned namespace %s for agent %s", ns_name, agent_id)
    return ns_name


async def ensure_deployment(
    namespace: str,
    agent_id: str,
    owner_id: str,
    policy: dict,
    min_pods: int,
    max_pods: int,
) -> dict:
    """Ensure Deployment+PVC+Service exist. Re-provisions the namespace if missing."""
    try:
        result = await k8s_apply(
            "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}"
        )
        if result.get("metadata", {}).get("name") == DEPLOYMENT_NAME:
            replicas = result.get("spec", {}).get("replicas", 0)
            if replicas == 0:
                await k8s_apply(
                    "PATCH",
                    f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}",
                    {"spec": {"replicas": min_pods or 1}},
                )
                logger.info("Scaled up idle deployment in %s to %d", namespace, min_pods or 1)
            return {"namespace": namespace, "created": False}
    except httpx.HTTPError:
        pass

    try:
        await k8s_apply("GET", f"/api/v1/namespaces/{namespace}")
    except httpx.HTTPError:
        logger.info("Namespace %s not found, re-provisioning", namespace)
        await provision_namespace(agent_id, owner_id, policy)

    await k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/persistentvolumeclaims",
        build_pvc_manifest(namespace, agent_id),
    )
    await k8s_apply(
        "POST",
        f"/apis/apps/v1/namespaces/{namespace}/deployments",
        build_deployment_manifest(
            namespace=namespace, agent_id=agent_id, min_pods=min_pods, policy=policy or {},
        ),
    )
    await k8s_apply(
        "POST",
        f"/api/v1/namespaces/{namespace}/services",
        build_service_manifest(namespace),
    )

    logger.info("Created Deployment for agent %s in namespace %s", agent_id, namespace)
    return {"namespace": namespace, "created": True}


async def get_deployment_status(namespace: str) -> dict:
    """Read deployment replica counts. Raises 404 if not found."""
    result = await k8s_apply(
        "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}"
    )
    status = result.get("status", {})
    return {
        "replicas": status.get("replicas", 0),
        "ready_replicas": status.get("readyReplicas", 0),
        "updated_replicas": status.get("updatedReplicas", 0),
    }


async def wait_for_ready(namespace: str, timeout: int) -> dict:
    """Long-poll until at least one replica is ready or the timeout fires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = await k8s_apply(
                "GET", f"/apis/apps/v1/namespaces/{namespace}/deployments/{DEPLOYMENT_NAME}"
            )
            status = result.get("status", {})
            if (status.get("readyReplicas") or 0) >= 1:
                return {"ready": True}
            for cond in status.get("conditions", []):
                if cond.get("type") == "Available" and cond.get("status") == "True":
                    return {"ready": True}
        except httpx.HTTPError:
            logger.debug("Deployment readiness poll failed for %s", namespace, exc_info=True)
        await asyncio.sleep(2)
    return {"ready": False}


async def cleanup_session_workspace(namespace: str, session_id: str) -> dict:
    """Best-effort: ask the runtime Pod to delete this session's workspace dir."""
    proxy_path = (
        f"/api/v1/namespaces/{namespace}/services/"
        f"{SERVICE_NAME}:{RUNTIME_PORT}/proxy/sessions/{session_id}/workspace"
    )
    try:
        return await k8s_apply("DELETE", proxy_path)
    except httpx.HTTPError:
        logger.info(
            "Session workspace cleanup skipped for %s in %s (pod not reachable)",
            session_id, namespace,
        )
        return {"status": "skipped", "reason": "pod_not_reachable"}

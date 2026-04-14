"""K3S IdentityBinder — SA + NetworkPolicy as an AWS-SG equivalent.

Egress profiles are pre-registered in a ConfigMap `egress-profiles` in the
`platform` namespace. Each profile is a list of NetworkPolicy egress rule
fragments. `bind_identity(agent_id, sa_name, sg_ref)` looks up the profile
named `sg_ref` and applies it as a NetworkPolicy selecting pods by
`aviary/agent-id={agent_id}` label.

This mirrors the EKS path where `sg_ref` is an AWS SG ID attached via
SecurityGroupPolicy — same protocol, different mechanism.
"""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import HTTPException

from aviary_shared.naming import (
    AGENTS_NAMESPACE,
    LABEL_AGENT_ID,
    PLATFORM_NAMESPACE,
    agent_network_policy_name,
)

from app.backends._common.k8s_client import apply_or_replace, k8s_apply
from app.backends.protocol import IdentityBinder

logger = logging.getLogger(__name__)

EGRESS_PROFILES_CONFIGMAP = "egress-profiles"
DEFAULT_PROFILE = "default"


async def _load_configmap() -> dict:
    try:
        return await k8s_apply(
            "GET",
            f"/api/v1/namespaces/{PLATFORM_NAMESPACE}/configmaps/{EGRESS_PROFILES_CONFIGMAP}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=503,
            detail=f"{EGRESS_PROFILES_CONFIGMAP} ConfigMap not reachable",
        ) from e


async def _load_merged_rules(sg_refs: list[str]) -> list[dict]:
    """Merge egress rule fragments from all named profiles.

    AWS SGs combine as a union of allow rules; we emulate that by concatenating
    the rule lists. K8s evaluates NetworkPolicy egress as a disjunction, so
    this yields the same "allowed if any rule permits" semantics.
    """
    cm = await _load_configmap()
    data = cm.get("data", {})
    merged: list[dict] = []
    for ref in sg_refs:
        raw = data.get(f"{ref}.json")
        if raw is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown egress profile '{ref}'",
            )
        merged.extend(json.loads(raw))
    return merged


class K3SIdentityBinder(IdentityBinder):
    async def ensure_service_account(self, sa_name: str) -> None:
        await k8s_apply(
            "POST",
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/serviceaccounts",
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {"name": sa_name, "namespace": AGENTS_NAMESPACE},
                "automountServiceAccountToken": False,
            },
        )

    async def bind_identity(self, agent_id: str, sa_name: str, sg_refs: list[str]) -> None:
        """Apply the merged profiles as a NetworkPolicy selecting the agent's pods."""
        if not sg_refs:
            raise HTTPException(status_code=400, detail="sg_refs must not be empty")
        egress_rules = await _load_merged_rules(sg_refs)
        name = agent_network_policy_name(agent_id)
        manifest = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": name,
                "namespace": AGENTS_NAMESPACE,
                "labels": {LABEL_AGENT_ID: agent_id},
            },
            "spec": {
                "podSelector": {"matchLabels": {LABEL_AGENT_ID: agent_id}},
                "policyTypes": ["Egress", "Ingress"],
                "ingress": [{}],
                "egress": egress_rules,
            },
        }
        await apply_or_replace(
            f"/apis/networking.k8s.io/v1/namespaces/{AGENTS_NAMESPACE}/networkpolicies",
            name,
            manifest,
        )
        logger.info("Bound identity for agent %s to profiles %s", agent_id, sg_refs)

    async def unbind_identity(self, agent_id: str) -> None:
        name = agent_network_policy_name(agent_id)
        await k8s_apply(
            "DELETE",
            f"/apis/networking.k8s.io/v1/namespaces/{AGENTS_NAMESPACE}/networkpolicies/{name}",
        )

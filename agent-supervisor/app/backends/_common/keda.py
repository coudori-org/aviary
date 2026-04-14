"""KEDA ScaledObject manifest for active-session-based autoscaling.

Trigger: PostgreSQL scaler counting active sessions per agent.
Target:  target = sessions_per_pod_target → replicas = ceil(count / target).

Requires a pre-provisioned TriggerAuthentication `aviary-postgres-auth` in the
`agents` namespace referencing a Secret `aviary-postgres-dsn` with key `connection`.
"""

from __future__ import annotations

from aviary_shared.naming import (
    AGENTS_NAMESPACE,
    agent_deployment_name,
    agent_scaledobject_name,
)

POSTGRES_TRIGGER_AUTH = "aviary-postgres-auth"


def build_scaledobject_manifest(
    agent_id: str,
    min_pods: int,
    max_pods: int,
    sessions_per_pod_target: int,
    idle_threshold_seconds: int,
    polling_interval: int = 30,
    cooldown_period: int = 300,
) -> dict:
    # Counts sessions with recent activity. A session whose last message is
    # older than `idle_threshold_seconds` is excluded so KEDA can scale
    # pods down when traffic subsides.
    query = (
        "SELECT COUNT(*) FROM sessions "
        f"WHERE agent_id='{agent_id}' "
        f"AND last_message_at > NOW() - INTERVAL '{idle_threshold_seconds} seconds'"
    )
    return {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {
            "name": agent_scaledobject_name(agent_id),
            "namespace": AGENTS_NAMESPACE,
        },
        "spec": {
            "scaleTargetRef": {"name": agent_deployment_name(agent_id)},
            "minReplicaCount": min_pods,
            "maxReplicaCount": max_pods,
            "pollingInterval": polling_interval,
            "cooldownPeriod": cooldown_period,
            "triggers": [
                {
                    "type": "postgresql",
                    "metadata": {
                        "query": query,
                        "targetQueryValue": str(sessions_per_pod_target),
                    },
                    "authenticationRef": {"name": POSTGRES_TRIGGER_AUTH},
                }
            ],
        },
    }

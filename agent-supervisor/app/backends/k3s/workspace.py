"""K3S WorkspaceStore — hostPath-backed per-agent PV + PVC.

Same WorkspaceStore interface as EKS (EFS-backed). K3S uses hostPath because
the cluster is single-node in dev; the PV is Retain so data survives rebuilds.
"""

from __future__ import annotations

import logging

import httpx

from aviary_shared.naming import (
    AGENTS_NAMESPACE,
    LABEL_AGENT_ID,
    PVC_SIZE,
    agent_pv_host_path,
    agent_pv_name,
    agent_pvc_name,
)

from app.backends._common.k8s_client import k8s_apply
from app.backends.protocol import WorkspaceRef, WorkspaceStore

logger = logging.getLogger(__name__)

SHARED_WORKSPACE_VOLUME = "shared-workspace"
WORKSPACE_VOLUME = "agent-workspace"
SHARED_WORKSPACE_HOST_PATH = "/workspace-shared"


class K3SWorkspaceStore(WorkspaceStore):
    async def ensure_agent_workspace(self, agent_id: str) -> WorkspaceRef:
        pv = agent_pv_name(agent_id)
        pvc = agent_pvc_name(agent_id)
        await k8s_apply("POST", "/api/v1/persistentvolumes", {
            "apiVersion": "v1",
            "kind": "PersistentVolume",
            "metadata": {"name": pv, "labels": {LABEL_AGENT_ID: agent_id}},
            "spec": {
                "capacity": {"storage": PVC_SIZE},
                "accessModes": ["ReadWriteOnce"],
                "persistentVolumeReclaimPolicy": "Retain",
                "storageClassName": "",
                "hostPath": {
                    "path": agent_pv_host_path(agent_id),
                    "type": "DirectoryOrCreate",
                },
                "claimRef": {"namespace": AGENTS_NAMESPACE, "name": pvc},
            },
        })
        await k8s_apply("POST", f"/api/v1/namespaces/{AGENTS_NAMESPACE}/persistentvolumeclaims", {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {
                "name": pvc,
                "namespace": AGENTS_NAMESPACE,
                "labels": {LABEL_AGENT_ID: agent_id},
            },
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": PVC_SIZE}},
                "storageClassName": "",
                "volumeName": pv,
            },
        })
        return WorkspaceRef(
            volume={
                "name": WORKSPACE_VOLUME,
                "persistentVolumeClaim": {"claimName": pvc},
            },
            volume_mount={"name": WORKSPACE_VOLUME, "mountPath": "/workspace"},
        )

    async def delete_agent_workspace(self, agent_id: str) -> None:
        pvc = agent_pvc_name(agent_id)
        pv = agent_pv_name(agent_id)
        await k8s_apply(
            "DELETE",
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/persistentvolumeclaims/{pvc}",
        )
        await k8s_apply("DELETE", f"/api/v1/persistentvolumes/{pv}")

    async def cleanup_session_workspace(self, agent_id: str, session_id: str) -> None:
        """Ask the runtime Pod (via Service proxy) to rm the session's workdir."""
        from aviary_shared.naming import RUNTIME_PORT, agent_service_name

        svc = agent_service_name(agent_id)
        path = (
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/services/"
            f"{svc}:{RUNTIME_PORT}/proxy/sessions/{session_id}/workspace"
        )
        try:
            await k8s_apply("DELETE", path)
        except httpx.HTTPError:
            logger.info(
                "Session workspace cleanup skipped for %s/%s (pod not reachable)",
                agent_id, session_id,
            )


def shared_workspace_volume() -> dict:
    return {
        "name": SHARED_WORKSPACE_VOLUME,
        "hostPath": {"path": SHARED_WORKSPACE_HOST_PATH, "type": "DirectoryOrCreate"},
    }


def shared_workspace_mount() -> dict:
    return {"name": SHARED_WORKSPACE_VOLUME, "mountPath": "/workspace-shared"}

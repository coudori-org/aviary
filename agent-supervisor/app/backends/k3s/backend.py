"""K3S RuntimeBackend — single `agents` namespace, hostPath workspace, KEDA scaling."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from aviary_shared.naming import (
    AGENTS_NAMESPACE,
    RUNTIME_PORT,
    agent_deployment_name,
    agent_scaledobject_name,
    agent_service_name,
)

from app.backends._common.k8s_client import apply_or_replace, k8s_apply
from app.backends._common.keda import build_scaledobject_manifest
from app.backends.k3s.identity import K3SIdentityBinder
from app.backends.k3s.manifests import (
    build_deployment_manifest,
    build_service_manifest,
)
from app.backends.k3s.workspace import K3SWorkspaceStore
from app.backends.protocol import (
    AgentSpec,
    DeploymentStatus,
    IdentityBinder,
    RuntimeBackend,
    WorkspaceStore,
)
from app.config import settings

logger = logging.getLogger(__name__)

_KEDA_GROUP = "/apis/keda.sh/v1alpha1"


class K3SBackend(RuntimeBackend):
    def __init__(self) -> None:
        self._workspace = K3SWorkspaceStore()
        self._identity = K3SIdentityBinder()

    @property
    def workspace(self) -> WorkspaceStore:
        return self._workspace

    @property
    def identity(self) -> IdentityBinder:
        return self._identity

    # ---- Lifecycle -------------------------------------------------------

    async def register_agent(self, spec: AgentSpec) -> None:
        await self._identity.ensure_service_account(spec.sa_name)
        workspace_ref = await self._workspace.ensure_agent_workspace(spec.agent_id)

        await apply_or_replace(
            f"/apis/apps/v1/namespaces/{AGENTS_NAMESPACE}/deployments",
            agent_deployment_name(spec.agent_id),
            build_deployment_manifest(spec, workspace_ref),
        )
        await apply_or_replace(
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/services",
            agent_service_name(spec.agent_id),
            build_service_manifest(spec.agent_id),
        )
        await self._ensure_scaledobject(spec)

    async def unregister_agent(self, agent_id: str) -> None:
        await self._identity.unbind_identity(agent_id)
        for path in [
            f"{_KEDA_GROUP}/namespaces/{AGENTS_NAMESPACE}/scaledobjects/{agent_scaledobject_name(agent_id)}",
            f"/apis/apps/v1/namespaces/{AGENTS_NAMESPACE}/deployments/{agent_deployment_name(agent_id)}",
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/services/{agent_service_name(agent_id)}",
        ]:
            await k8s_apply("DELETE", path)
        await self._workspace.delete_agent_workspace(agent_id)
        logger.info("Unregistered agent %s", agent_id)

    async def _ensure_scaledobject(self, spec: AgentSpec) -> None:
        manifest = build_scaledobject_manifest(
            agent_id=spec.agent_id,
            min_pods=spec.min_pods,
            max_pods=spec.max_pods,
            sessions_per_pod_target=settings.max_concurrent_sessions_per_pod,
        )
        try:
            await apply_or_replace(
                f"{_KEDA_GROUP}/namespaces/{AGENTS_NAMESPACE}/scaledobjects",
                agent_scaledobject_name(spec.agent_id),
                manifest,
            )
        except httpx.HTTPError:
            logger.warning(
                "KEDA ScaledObject apply failed for agent %s (KEDA not installed?)",
                spec.agent_id, exc_info=True,
            )

    # ---- Activation ------------------------------------------------------

    async def ensure_active(self, agent_id: str) -> None:
        dep = await self._get_deployment(agent_id)
        if dep is None:
            return
        replicas = dep.get("spec", {}).get("replicas", 0)
        if replicas == 0:
            await self.scale(agent_id, 1)

    async def is_ready(self, agent_id: str) -> bool:
        status = await self.get_status(agent_id)
        return status.ready_replicas >= 1

    async def wait_ready(self, agent_id: str, timeout_s: int) -> bool:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if await self.is_ready(agent_id):
                return True
            await asyncio.sleep(2)
        return False

    async def resolve_endpoint(self, agent_id: str) -> str:
        """Return the K8s API Service proxy path for the agent runtime."""
        svc = agent_service_name(agent_id)
        return (
            f"/api/v1/namespaces/{AGENTS_NAMESPACE}/services/"
            f"{svc}:{RUNTIME_PORT}/proxy"
        )

    # ---- Admin ops -------------------------------------------------------

    async def get_status(self, agent_id: str) -> DeploymentStatus:
        dep = await self._get_deployment(agent_id)
        if dep is None:
            return DeploymentStatus(exists=False)
        status = dep.get("status", {})
        return DeploymentStatus(
            exists=True,
            replicas=status.get("replicas", 0) or 0,
            ready_replicas=status.get("readyReplicas", 0) or 0,
            updated_replicas=status.get("updatedReplicas", 0) or 0,
        )

    async def restart(self, agent_id: str) -> None:
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{AGENTS_NAMESPACE}/deployments/{agent_deployment_name(agent_id)}",
            {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {"aviary/restartedAt": str(int(time.time()))}
                        }
                    }
                }
            },
        )

    async def scale(self, agent_id: str, replicas: int) -> None:
        await k8s_apply(
            "PATCH",
            f"/apis/apps/v1/namespaces/{AGENTS_NAMESPACE}/deployments/{agent_deployment_name(agent_id)}",
            {"spec": {"replicas": replicas}},
        )

    async def health(self) -> bool:
        try:
            await k8s_apply("GET", f"/api/v1/namespaces/{AGENTS_NAMESPACE}")
            return True
        except httpx.HTTPError:
            return False

    # ---- Internal --------------------------------------------------------

    async def _get_deployment(self, agent_id: str) -> dict | None:
        try:
            return await k8s_apply(
                "GET",
                f"/apis/apps/v1/namespaces/{AGENTS_NAMESPACE}/deployments/{agent_deployment_name(agent_id)}",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

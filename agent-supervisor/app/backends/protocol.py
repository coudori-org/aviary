"""Backend Protocol — platform-neutral contract for agent runtime management.

Three sub-protocols compose RuntimeBackend:
  - WorkspaceStore: per-agent/session workspace volume provisioning (EFS model).
  - IdentityBinder: SA creation + SG (or equivalent) binding for egress control.
  - RuntimeBackend: lifecycle, activation, SSE endpoint resolution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WorkspaceRef:
    """Volume descriptor injected into a Pod spec.

    The backend owns the decision of whether this is a PVC, hostPath, or
    CSI volume. The manifest builder renders `volume` and `volume_mount`
    into the pod spec without caring about the underlying storage.
    """

    volume: dict
    volume_mount: dict


@dataclass
class AgentSpec:
    agent_id: str
    owner_id: str
    image: str
    sa_name: str
    min_pods: int = 0
    max_pods: int = 3
    cpu_limit: str = "4"
    memory_limit: str = "4Gi"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class DeploymentStatus:
    exists: bool
    replicas: int = 0
    ready_replicas: int = 0
    updated_replicas: int = 0


class WorkspaceStore(ABC):
    @abstractmethod
    async def ensure_agent_workspace(self, agent_id: str) -> WorkspaceRef: ...

    @abstractmethod
    async def delete_agent_workspace(self, agent_id: str) -> None: ...

    @abstractmethod
    async def cleanup_session_workspace(self, agent_id: str, session_id: str) -> None: ...


class IdentityBinder(ABC):
    """Creates ServiceAccounts and binds them to an egress identity.

    `sg_ref` is a platform-specific opaque reference:
      - EKS:  AWS Security Group ID (sg-xxx)
      - K3S:  name of a pre-registered egress profile (see egress-profiles ConfigMap)
    """

    @abstractmethod
    async def ensure_service_account(self, sa_name: str) -> None: ...

    @abstractmethod
    async def bind_identity(self, agent_id: str, sa_name: str, sg_ref: str) -> None: ...

    @abstractmethod
    async def unbind_identity(self, agent_id: str) -> None: ...


class RuntimeBackend(ABC):
    @property
    @abstractmethod
    def workspace(self) -> WorkspaceStore: ...

    @property
    @abstractmethod
    def identity(self) -> IdentityBinder: ...

    @abstractmethod
    async def register_agent(self, spec: AgentSpec) -> None:
        """Create Deployment + Service + ScaledObject. Idempotent."""

    @abstractmethod
    async def unregister_agent(self, agent_id: str) -> None:
        """Tear down all per-agent resources."""

    @abstractmethod
    async def ensure_active(self, agent_id: str) -> None:
        """Activator: if replicas==0, patch to 1. KEDA handles N>1."""

    @abstractmethod
    async def is_ready(self, agent_id: str) -> bool: ...

    @abstractmethod
    async def wait_ready(self, agent_id: str, timeout_s: int) -> bool: ...

    @abstractmethod
    async def resolve_endpoint(self, agent_id: str) -> str:
        """Return a URL the common SSE proxy can stream from. Typically K8s Service DNS."""

    @abstractmethod
    async def get_status(self, agent_id: str) -> DeploymentStatus: ...

    @abstractmethod
    async def restart(self, agent_id: str) -> None: ...

    @abstractmethod
    async def scale(self, agent_id: str, replicas: int) -> None: ...

    @abstractmethod
    async def health(self) -> bool: ...

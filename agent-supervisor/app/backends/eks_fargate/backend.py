"""EKS Fargate backend — stub. Follow-up PR.

Planned differences from EKS Native:
- WorkspaceStore: EFS Access Point per agent (ReadWriteMany).
- IdentityBinder: SecurityGroupPolicy (VPC CNI) binding pre-created SGs.
- Manifests: Fargate tier rounding for resource requests.
"""

from app.backends.protocol import RuntimeBackend


def _not_impl(*_a, **_k):
    raise NotImplementedError("EKS Fargate backend not yet implemented")


class EKSFargateBackend(RuntimeBackend):
    workspace = property(lambda self: _not_impl())
    identity = property(lambda self: _not_impl())
    register_agent = _not_impl
    unregister_agent = _not_impl
    ensure_active = _not_impl
    is_ready = _not_impl
    wait_ready = _not_impl
    resolve_endpoint = _not_impl
    get_status = _not_impl
    restart = _not_impl
    scale = _not_impl
    health = _not_impl

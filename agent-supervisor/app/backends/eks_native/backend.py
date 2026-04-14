"""EKS Native backend — stub. Follow-up PR."""

from app.backends.protocol import RuntimeBackend


def _not_impl(*_a, **_k):
    raise NotImplementedError("EKS Native backend not yet implemented")


class EKSNativeBackend(RuntimeBackend):
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

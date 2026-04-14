"""Backend factory — selects a RuntimeBackend implementation by BACKEND_KIND."""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.backends.protocol import RuntimeBackend


@lru_cache(maxsize=1)
def create_backend() -> RuntimeBackend:
    kind = settings.backend_kind.lower()
    if kind == "k3s":
        from app.backends.k3s.backend import K3SBackend
        return K3SBackend()
    if kind == "eks_native":
        from app.backends.eks_native.backend import EKSNativeBackend
        return EKSNativeBackend()
    if kind == "eks_fargate":
        from app.backends.eks_fargate.backend import EKSFargateBackend
        return EKSFargateBackend()
    raise ValueError(f"Unknown BACKEND_KIND: {settings.backend_kind}")


def get_backend() -> RuntimeBackend:
    """FastAPI dependency."""
    return create_backend()

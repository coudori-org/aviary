"""Runtime endpoint resolution.

The supervisor is stateless — the caller passes the target agent's
`runtime_endpoint` inside `agent_config`. Null falls back to the
configured default environment endpoint.
"""

from app.config import settings


def resolve_runtime_base(runtime_endpoint: str | None) -> str:
    return runtime_endpoint or settings.supervisor_default_runtime_endpoint

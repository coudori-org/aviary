"""Runtime endpoint resolution.

The supervisor is stateless — the caller (API / Temporal) passes the agent's
`runtime_endpoint` in each publish request body. Null falls back to the
configured default environment endpoint.
"""

from app.config import settings


def resolve_runtime_base(runtime_endpoint: str | None) -> str:
    """Return the runtime base URL for a request."""
    return runtime_endpoint or settings.supervisor_default_runtime_endpoint

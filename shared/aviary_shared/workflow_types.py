"""Shared data contracts for Temporal workflow I/O.

Kept here (not in worker/ or api/) so both the Temporal client (api) and
the worker see the exact same dataclass — JSON field names match, which
keeps deserialization predictable on the worker side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowRunInput:
    run_id: str                        # = Temporal workflow_id and WorkflowRun.id
    owner_external_id: str             # OIDC sub — supervisor worker-auth fallback
    definition_snapshot: dict[str, Any]
    trigger_data: dict[str, Any] = field(default_factory=dict)
    # JWT of the triggering user. Forwarded through supervisor → runtime →
    # LiteLLM so per-user credential lookup works exactly as in chat.
    # Unset for cron / webhook triggers (worker-auth fallback kicks in).
    user_token: str | None = None
    # Optional per-workflow runtime endpoint override. None → supervisor
    # resolves to its configured default environment.
    runtime_endpoint: str | None = None
    resume_context: dict[str, Any] | None = None
    # Shared key for artifact storage across a resume chain. Fresh runs get
    # their own run_id here; resumed runs inherit the source's root_run_id.
    root_run_id: str | None = None


@dataclass
class WorkflowRunResult:
    status: str                        # "completed" | "cancelled" | "failed"

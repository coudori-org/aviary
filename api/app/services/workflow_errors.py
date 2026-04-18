"""Typed exceptions for workflow services — the app registers an
exception handler that maps each class to the right HTTP status, so
routers don't need to repeat try/except ValueError plumbing."""

from __future__ import annotations


class WorkflowError(Exception):
    """Base class — don't raise this directly; pick a subclass."""

    http_status: int = 400


class WorkflowConflictError(WorkflowError):
    """Persistent-resource collision (e.g. slug already taken). HTTP 409."""

    http_status = 409


class WorkflowStateError(WorkflowError):
    """State transition not possible with the current workflow / run
    (e.g. deployed run requested with no deploy, nothing to resume).
    HTTP 400."""

    http_status = 400

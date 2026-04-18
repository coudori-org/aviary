"""Typed domain exceptions + FastAPI handler wiring.

Services raise these instead of ``HTTPException`` so HTTP concerns stay
in the router layer. ``main.py`` registers one exception handler that
maps every ``DomainError`` subclass to the right status via ``http_status``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base class — don't raise directly; pick a subclass."""

    http_status: int = 400


class ConflictError(DomainError):
    """Persistent-resource collision (e.g. slug already taken). HTTP 409."""

    http_status = 409


class StateError(DomainError):
    """State transition not possible with the current resource
    (e.g. deployed run requested with no deploy, nothing to resume). HTTP 400."""

    http_status = 400


class NotFoundError(DomainError):
    """Resource missing or not visible to the caller. HTTP 404."""

    http_status = 404


class UnauthorizedError(DomainError):
    """Caller lacks permission for the requested action. HTTP 403."""

    http_status = 403


class UpstreamError(DomainError):
    """An upstream dependency (LLM, supervisor, Vault, …) returned
    something we can't act on. HTTP 502 so the caller treats it as a
    transient infrastructure failure, not a user input problem."""

    http_status = 502


def register_handlers(app: FastAPI) -> None:
    """Install the single DomainError → HTTP mapping."""

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": str(exc)},
        )

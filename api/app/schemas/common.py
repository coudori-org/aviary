from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: UUID
    external_id: str
    email: str
    display_name: str
    avatar_url: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class PreferencesUpdateRequest(BaseModel):
    """Partial update for user.preferences. Top-level keys in the request
    body replace the corresponding keys; other keys are preserved."""

    preferences: dict[str, Any]


class AuthConfigResponse(BaseModel):
    issuer: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str


class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: str
    code_verifier: str


class LogoutRequest(BaseModel):
    # Where the IdP should send the browser after logging out. Frontend
    # passes its own origin + desired path (usually `/login`).
    post_logout_redirect_uri: str | None = None


class LogoutResponse(BaseModel):
    # URL the browser should navigate to for RP-initiated logout at the IdP.
    # Empty string if the IdP has no end_session endpoint or the session
    # was already gone — the caller should just redirect locally.
    end_session_url: str = ""


class ErrorResponse(BaseModel):
    detail: str

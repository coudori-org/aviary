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


class TokenExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int
    user: UserResponse


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int


class ErrorResponse(BaseModel):
    detail: str

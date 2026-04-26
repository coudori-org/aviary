"""Per-user credential schemas surfaced to the settings screen."""

from pydantic import BaseModel, Field


class CredentialKeyStatus(BaseModel):
    key: str
    label: str
    configured: bool


class CredentialNamespace(BaseModel):
    namespace: str
    label: str
    description: str | None = None
    keys: list[CredentialKeyStatus]


class CredentialsResponse(BaseModel):
    vault_enabled: bool
    namespaces: list[CredentialNamespace]


class CredentialWriteRequest(BaseModel):
    value: str = Field(min_length=1)

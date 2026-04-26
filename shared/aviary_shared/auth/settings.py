from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from aviary_shared.auth.oidc import OIDCValidator


class IdpSettings(BaseModel):
    oidc_issuer: str | None = None
    oidc_internal_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    dev_user_sub: str = "dev-user"


class _OidcConfigLike(Protocol):
    oidc_issuer: str | None
    oidc_internal_issuer: str | None
    dev_user_sub: str


def build_oidc_validator(config: _OidcConfigLike) -> OIDCValidator:
    return OIDCValidator(
        issuer=config.oidc_issuer or None,
        internal_issuer=config.oidc_internal_issuer,
        dev_user_sub=getattr(config, "dev_user_sub", "dev-user"),
    )

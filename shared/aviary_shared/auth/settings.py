"""Shared IdP config — reference schema + validator-construction helper.

Every service defines its own `Settings` (pydantic-settings) because each
carries service-specific knobs, but the OIDC block is identical across
services. This module centralizes:

- The canonical OIDC env var schema (`IdpSettings` — reference only).
- `build_oidc_validator(...)` — one-shot constructor that selects the
  correct `ClaimMapper` from `oidc_provider` and wires up an `OIDCValidator`.

Services just call `build_oidc_validator(settings)` where `settings` is any
object exposing `oidc_provider / oidc_issuer / oidc_internal_issuer /
oidc_audience`. Switching IdP = change env vars.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from aviary_shared.auth.claims import get_claim_mapper
from aviary_shared.auth.oidc import OIDCValidator


class IdpSettings(BaseModel):
    """Canonical OIDC env var schema. Services may copy these fields into
    their own Settings class or compose this in — either is fine. The
    field names here are the source of truth."""

    oidc_provider: str = "keycloak"
    oidc_issuer: str
    oidc_internal_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_client_id: str | None = None


class _OidcConfigLike(Protocol):
    """Duck-typed view of any Settings object with OIDC fields."""

    oidc_provider: str
    oidc_issuer: str
    oidc_internal_issuer: str | None
    oidc_audience: str | None


def build_oidc_validator(config: _OidcConfigLike) -> OIDCValidator:
    """Construct an `OIDCValidator` wired for the configured provider.

    The only IdP-specific behavior — claim shape — is selected here via
    `oidc_provider`. Everything else is plain OIDC.
    """
    return OIDCValidator(
        issuer=config.oidc_issuer,
        internal_issuer=config.oidc_internal_issuer,
        audience=config.oidc_audience,
        claim_mapper=get_claim_mapper(config.oidc_provider),
    )

"""IdP-specific claim mapping.

`OIDCValidator` handles generic OIDC plumbing (discovery, JWKS, RS256 verify).
The shape of the resulting JWT payload, however, is IdP-specific:

- Keycloak buries roles under `realm_access.roles` (or a flattened `realm_roles`
  client mapper) and emits groups with a leading `/`.
- Okta uses custom claims for roles/groups (no envelope) and follows the
  standard OIDC `groups` shape.
- Generic providers may have no role/group claims at all.

This module defines the `ClaimMapper` protocol and ships three implementations.
Services pick one via `OIDC_PROVIDER` (see `IdpSettings`).

To support a new IdP: add a subclass here, register it in `get_claim_mapper`,
and set `OIDC_PROVIDER=<name>` at deploy time. No other code should need to
change.
"""

from __future__ import annotations

from typing import Protocol

from aviary_shared.auth.oidc import TokenClaims


class ClaimMapper(Protocol):
    """Maps a verified JWT payload (dict) to domain-level `TokenClaims`."""

    def map(self, payload: dict) -> TokenClaims: ...


def _common_identity(payload: dict) -> tuple[str, str, str]:
    sub = payload.get("sub")
    if not sub:
        raise ValueError("Token missing 'sub' claim")
    email = payload.get("email", "")
    display_name = (
        payload.get("name")
        or payload.get("preferred_username")
        or email
    )
    return sub, email, display_name


class KeycloakClaimMapper:
    """Keycloak realm/client role + group envelope."""

    def map(self, payload: dict) -> TokenClaims:
        sub, email, display_name = _common_identity(payload)

        roles: list[str] = []
        if "realm_roles" in payload:
            roles = payload["realm_roles"] or []
        elif "realm_access" in payload:
            roles = payload.get("realm_access", {}).get("roles", []) or []

        raw_groups: list[str] = payload.get("groups", []) or []
        groups = [g.lstrip("/") for g in raw_groups if g]

        return TokenClaims(
            sub=sub, email=email, display_name=display_name, roles=roles, groups=groups
        )


class OktaClaimMapper:
    """Okta custom-claim shape — roles/groups are top-level arrays (no envelope).

    Okta surfaces group membership via the standard `groups` claim when an
    authorization-server group claim is configured. Roles are convention —
    Okta has no built-in role concept, so we read a `roles` claim that an
    operator configures on the auth server.
    """

    def map(self, payload: dict) -> TokenClaims:
        sub, email, display_name = _common_identity(payload)
        roles: list[str] = payload.get("roles", []) or []
        groups: list[str] = payload.get("groups", []) or []
        return TokenClaims(
            sub=sub, email=email, display_name=display_name, roles=roles, groups=groups
        )


class GenericOIDCClaimMapper:
    """Plain OIDC — only the standard identity claims. No roles, no groups."""

    def map(self, payload: dict) -> TokenClaims:
        sub, email, display_name = _common_identity(payload)
        return TokenClaims(sub=sub, email=email, display_name=display_name)


_MAPPERS: dict[str, type] = {
    "keycloak": KeycloakClaimMapper,
    "okta": OktaClaimMapper,
    "generic": GenericOIDCClaimMapper,
}


def get_claim_mapper(provider: str) -> ClaimMapper:
    try:
        return _MAPPERS[provider.lower()]()
    except KeyError as exc:
        raise ValueError(
            f"Unknown OIDC_PROVIDER={provider!r}. "
            f"Supported: {sorted(_MAPPERS)}"
        ) from exc

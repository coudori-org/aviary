"""OIDC auth — thin wrapper over the shared validator. See api/app/auth/oidc.py."""

from aviary_shared.auth import build_oidc_validator
from aviary_shared.auth.oidc import TokenClaims  # noqa: F401 — re-exported

from app.config import settings

_validator = build_oidc_validator(settings)


async def init_oidc() -> None:
    await _validator.init()


async def validate_token(token: str) -> TokenClaims:
    return await _validator.validate_token(token)

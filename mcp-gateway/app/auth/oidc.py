"""OIDC auth — thin wrapper over shared OIDCValidator."""

from aviary_shared.auth.oidc import OIDCValidator, TokenClaims  # noqa: F401

from app.config import settings

_validator = OIDCValidator(
    issuer=settings.oidc_issuer,
    internal_issuer=settings.oidc_internal_issuer,
    audience=settings.oidc_audience,
)


async def init_oidc() -> None:
    await _validator.init()


async def validate_token(token: str) -> TokenClaims:
    return await _validator.validate_token(token)

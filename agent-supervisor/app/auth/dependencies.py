"""FastAPI dependency for extracting and validating the caller's user JWT."""

from fastapi import HTTPException, Request

from app.auth.oidc import TokenClaims, validate_token


async def get_current_user(request: Request) -> TokenClaims:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(None, 1)[1].strip()
    try:
        return await validate_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def extract_bearer_token(request: Request) -> str:
    """Return the raw Bearer token string without validating it.

    Used when we need to forward the token to the runtime after already
    validating it via `get_current_user`.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return auth_header.split(None, 1)[1].strip()

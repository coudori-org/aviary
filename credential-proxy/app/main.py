"""Credential Proxy — intercepts requests from session Pods, injects secrets from Vault.

Session Pods send requests to this proxy with headers:
  X-Session-ID: <session_id>
  X-Credential-Name: <credential_name> (e.g., GITHUB_TOKEN)
  X-Target-URL: <target_api_url>

The proxy:
1. Looks up session → agent → credential vault_path
2. Fetches the secret from Vault
3. Injects it as Authorization header
4. Forwards the request to the target URL
"""

import httpx
from fastapi import FastAPI, Request, Response

from app.session_resolver import get_credentials_for_session
from app.vault_client import get_secret

app = FastAPI(title="AgentBox Credential Proxy", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.api_route("/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_request(request: Request):
    """Proxy an outbound request with credential injection."""
    session_id = request.headers.get("X-Session-ID")
    credential_name = request.headers.get("X-Credential-Name")
    target_url = request.headers.get("X-Target-URL")

    if not session_id or not credential_name or not target_url:
        return Response(
            content='{"error": "Missing X-Session-ID, X-Credential-Name, or X-Target-URL header"}',
            status_code=400,
            media_type="application/json",
        )

    # Look up credentials for this session
    credentials = await get_credentials_for_session(session_id)
    cred = next((c for c in credentials if c["name"] == credential_name), None)

    if not cred:
        return Response(
            content=f'{{"error": "Credential \'{credential_name}\' not found for this session"}}',
            status_code=404,
            media_type="application/json",
        )

    # Fetch secret from Vault
    secret_value = await get_secret(cred["vault_path"])
    if not secret_value:
        return Response(
            content='{"error": "Secret not found in Vault"}',
            status_code=502,
            media_type="application/json",
        )

    # Build outbound request with injected credential
    body = await request.body()
    outbound_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in (
            "host", "x-session-id", "x-credential-name", "x-target-url",
            "content-length", "transfer-encoding",
        )
    }
    outbound_headers["Authorization"] = f"Bearer {secret_value}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=outbound_headers,
            content=body if body else None,
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )

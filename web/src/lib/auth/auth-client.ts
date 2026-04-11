import type { AuthConfig } from "@/types";
import { tokenStorage } from "./storage";
import { generatePkce, generateState } from "./pkce";

/**
 * OIDC PKCE flow against Keycloak.
 *
 * The browser never holds a token — `/api/auth/callback` exchanges the
 * code on the server, stores the tokens in Redis, and sets an httpOnly
 * session cookie. Every subsequent fetch / WebSocket carries that
 * cookie automatically; the API server handles refresh.
 */

let _configPromise: Promise<AuthConfig> | null = null;

export async function fetchAuthConfig(): Promise<AuthConfig> {
  if (!_configPromise) {
    _configPromise = fetch("/api/auth/config", { credentials: "include" }).then((res) => {
      if (!res.ok) throw new Error("Failed to fetch auth config");
      return res.json();
    });
  }
  return _configPromise;
}

export async function initiateLogin(): Promise<void> {
  const config = await fetchAuthConfig();
  const { codeVerifier, codeChallenge } = await generatePkce();
  const state = generateState();

  tokenStorage.setPkce(codeVerifier, state);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.client_id,
    redirect_uri: `${window.location.origin}/auth/callback`,
    scope: "openid profile email",
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    state,
  });

  window.location.href = `${config.authorization_endpoint}?${params}`;
}

export async function handleCallback(code: string, state: string): Promise<void> {
  const savedState = tokenStorage.getAuthState();
  if (state !== savedState) {
    throw new Error("Invalid state parameter — possible CSRF attack");
  }

  const codeVerifier = tokenStorage.getPkceVerifier();
  if (!codeVerifier) {
    throw new Error("Missing PKCE code verifier");
  }

  const res = await fetch("/api/auth/callback", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      redirect_uri: `${window.location.origin}/auth/callback`,
      code_verifier: codeVerifier,
    }),
  });

  tokenStorage.clearPkce();

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || res.statusText || "Auth callback failed");
  }
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  } catch {
    // Logout must always succeed locally — fall through to redirect.
  }

  try {
    const config = await fetchAuthConfig();
    if (config.end_session_endpoint) {
      const params = new URLSearchParams({
        post_logout_redirect_uri: `${window.location.origin}/login`,
        client_id: config.client_id,
      });
      window.location.href = `${config.end_session_endpoint}?${params}`;
      return;
    }
  } catch {
    // OIDC discovery failed — fall through to local redirect.
  }

  window.location.href = "/login";
}

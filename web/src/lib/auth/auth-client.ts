import type { AuthConfig } from "@/types";
import { tokenStorage } from "./storage";
import { generatePkce, generateState } from "./pkce";

/**
 * Auth client — OIDC PKCE flow against Keycloak (or any OIDC provider).
 *
 * The browser communicates directly with the public Keycloak URL for token
 * refresh; the API server proxies the initial code-for-token exchange so it
 * can rewrite issuer URLs internally.
 */

const REFRESH_BUFFER_SECONDS = 60;

let _configPromise: Promise<AuthConfig> | null = null;
let _refreshPromise: Promise<boolean> | null = null;

export async function fetchAuthConfig(): Promise<AuthConfig> {
  if (!_configPromise) {
    _configPromise = fetch("/api/auth/config").then((res) => {
      if (!res.ok) throw new Error("Failed to fetch auth config");
      return res.json();
    });
  }
  return _configPromise;
}

export function isAuthenticated(): boolean {
  return !!tokenStorage.getAccessToken();
}

export function isTokenExpired(): boolean {
  const expiresAt = tokenStorage.getExpiresAt();
  if (!expiresAt) return true;
  return Date.now() >= expiresAt - REFRESH_BUFFER_SECONDS * 1000;
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

  tokenStorage.setTokens(await res.json());
}

/**
 * Refresh the access token. Deduplicates concurrent requests.
 * Returns false if refresh failed (caller should logout).
 */
export async function refreshAccessToken(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (!refreshToken) return false;

    try {
      // Refresh against Keycloak directly to avoid issuer URL rewriting issues.
      const config = await fetchAuthConfig();
      const res = await fetch(config.token_endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "refresh_token",
          client_id: config.client_id,
          refresh_token: refreshToken,
        }),
      });

      if (!res.ok) return false;
      tokenStorage.setTokens(await res.json());
      return true;
    } catch {
      return false;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

/** Returns a valid access token (refreshing if expired), or null if user must re-login. */
export async function ensureValidToken(): Promise<string | null> {
  const token = tokenStorage.getAccessToken();
  if (!token) return null;
  if (!isTokenExpired()) return token;

  const refreshed = await refreshAccessToken();
  return refreshed ? tokenStorage.getAccessToken() : null;
}

export async function logout(): Promise<void> {
  const idToken = tokenStorage.getIdToken();

  tokenStorage.clearTokens();
  tokenStorage.clearPkce();

  // Try Keycloak end_session_endpoint with id_token_hint for global SSO logout
  try {
    const config = await fetchAuthConfig();
    if (config.end_session_endpoint && idToken) {
      const params = new URLSearchParams({
        id_token_hint: idToken,
        post_logout_redirect_uri: `${window.location.origin}/login`,
      });
      window.location.href = `${config.end_session_endpoint}?${params}`;
      return;
    }
  } catch {
    // OIDC discovery failed — fall through to local redirect.
    // This is the only place we swallow an error: logout must always succeed
    // from the user's perspective.
  }

  window.location.href = "/login";
}

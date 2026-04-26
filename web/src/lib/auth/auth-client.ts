import type { AuthConfig } from "@/types";
import { tokenStorage } from "./storage";
import { generatePkce, generateState } from "./pkce";

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

async function devLogin(): Promise<void> {
  const res = await fetch("/api/auth/dev-login", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || res.statusText || "Dev login failed");
  }
}

export async function initiateLogin(): Promise<void> {
  const config = await fetchAuthConfig();

  if (!config.idp_enabled) {
    await devLogin();
    window.location.href = "/";
    return;
  }

  const { codeVerifier, codeChallenge } = await generatePkce();
  const state = generateState();

  tokenStorage.setPkce(codeVerifier, state);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.client_id,
    redirect_uri: `${window.location.origin}/auth/callback`,
    scope: "openid profile email offline_access",
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
  // server builds end_session URL (with id_token_hint for Okta); empty in null mode
  let endSessionUrl = "";
  try {
    const res = await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        post_logout_redirect_uri: `${window.location.origin}/login`,
      }),
    });
    if (res.ok) {
      const body = (await res.json().catch(() => null)) as { end_session_url?: string } | null;
      endSessionUrl = body?.end_session_url ?? "";
    }
  } catch {
    // Logout must always succeed locally — fall through to redirect.
  }

  window.location.href = endSessionUrl || "/login";
}

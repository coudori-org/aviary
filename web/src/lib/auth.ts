import type { AuthConfig } from "@/types";

const STORAGE_KEY_VERIFIER = "aviary_pkce_verifier";
const STORAGE_KEY_STATE = "aviary_auth_state";
const STORAGE_KEY_TOKEN = "aviary_access_token";
const STORAGE_KEY_ID_TOKEN = "aviary_id_token";

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, length);
}

async function sha256(plain: string): Promise<ArrayBuffer> {
  const encoder = new TextEncoder();
  return crypto.subtle.digest("SHA-256", encoder.encode(plain));
}

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function generatePKCE(): Promise<{
  codeVerifier: string;
  codeChallenge: string;
}> {
  const codeVerifier = generateRandomString(64);
  const hashed = await sha256(codeVerifier);
  const codeChallenge = base64UrlEncode(hashed);
  return { codeVerifier, codeChallenge };
}

export async function fetchAuthConfig(): Promise<AuthConfig> {
  const res = await fetch("/api/auth/config");
  if (!res.ok) throw new Error("Failed to fetch auth config");
  return res.json();
}

export async function initiateLogin(): Promise<void> {
  const config = await fetchAuthConfig();
  const { codeVerifier, codeChallenge } = await generatePKCE();
  const state = generateRandomString(32);

  sessionStorage.setItem(STORAGE_KEY_VERIFIER, codeVerifier);
  sessionStorage.setItem(STORAGE_KEY_STATE, state);

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

export async function handleCallback(
  code: string,
  state: string
): Promise<{ accessToken: string }> {
  const savedState = sessionStorage.getItem(STORAGE_KEY_STATE);
  if (state !== savedState) {
    throw new Error("Invalid state parameter — possible CSRF attack");
  }

  const codeVerifier = sessionStorage.getItem(STORAGE_KEY_VERIFIER);
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

  // Clean up PKCE state regardless of outcome
  sessionStorage.removeItem(STORAGE_KEY_VERIFIER);
  sessionStorage.removeItem(STORAGE_KEY_STATE);

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Auth callback failed" }));
    throw new Error(error.detail);
  }

  const data = await res.json();
  localStorage.setItem(STORAGE_KEY_TOKEN, data.access_token);
  // Store id_token for logout (Keycloak requires id_token_hint)
  if (data.id_token) {
    localStorage.setItem(STORAGE_KEY_ID_TOKEN, data.id_token);
  }
  return { accessToken: data.access_token };
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(STORAGE_KEY_TOKEN);
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

export async function logout(): Promise<void> {
  const idToken = localStorage.getItem(STORAGE_KEY_ID_TOKEN);

  // Clear all stored tokens
  localStorage.removeItem(STORAGE_KEY_TOKEN);
  localStorage.removeItem(STORAGE_KEY_ID_TOKEN);
  sessionStorage.removeItem(STORAGE_KEY_VERIFIER);
  sessionStorage.removeItem(STORAGE_KEY_STATE);

  // Redirect to Keycloak end_session_endpoint with id_token_hint
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
    // Ignore — fall through to local redirect
  }

  window.location.href = "/login";
}

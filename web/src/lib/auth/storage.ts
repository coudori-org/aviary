/**
 * Token storage — encapsulates localStorage/sessionStorage access for OIDC tokens.
 *
 * No business logic, just typed get/set/remove. The auth-client builds on top.
 */

const KEYS = {
  accessToken: "aviary_access_token",
  refreshToken: "aviary_refresh_token",
  idToken: "aviary_id_token",
  expiresAt: "aviary_token_expires_at",
  pkceVerifier: "aviary_pkce_verifier",
  authState: "aviary_auth_state",
} as const;

function isBrowser() {
  return typeof window !== "undefined";
}

export const tokenStorage = {
  // Persistent (localStorage) — survives reload
  getAccessToken(): string | null {
    return isBrowser() ? localStorage.getItem(KEYS.accessToken) : null;
  },
  getRefreshToken(): string | null {
    return isBrowser() ? localStorage.getItem(KEYS.refreshToken) : null;
  },
  getIdToken(): string | null {
    return isBrowser() ? localStorage.getItem(KEYS.idToken) : null;
  },
  getExpiresAt(): number | null {
    if (!isBrowser()) return null;
    const v = localStorage.getItem(KEYS.expiresAt);
    return v ? Number(v) : null;
  },

  setTokens(data: {
    access_token: string;
    refresh_token?: string | null;
    id_token?: string | null;
    expires_in?: number;
  }) {
    if (!isBrowser()) return;
    localStorage.setItem(KEYS.accessToken, data.access_token);
    if (data.refresh_token) localStorage.setItem(KEYS.refreshToken, data.refresh_token);
    if (data.id_token) localStorage.setItem(KEYS.idToken, data.id_token);
    const expiresIn = data.expires_in ?? 300;
    localStorage.setItem(KEYS.expiresAt, String(Date.now() + expiresIn * 1000));
  },

  clearTokens() {
    if (!isBrowser()) return;
    localStorage.removeItem(KEYS.accessToken);
    localStorage.removeItem(KEYS.refreshToken);
    localStorage.removeItem(KEYS.idToken);
    localStorage.removeItem(KEYS.expiresAt);
  },

  // Ephemeral (sessionStorage) — for PKCE flow
  setPkce(verifier: string, state: string) {
    if (!isBrowser()) return;
    sessionStorage.setItem(KEYS.pkceVerifier, verifier);
    sessionStorage.setItem(KEYS.authState, state);
  },
  getPkceVerifier(): string | null {
    return isBrowser() ? sessionStorage.getItem(KEYS.pkceVerifier) : null;
  },
  getAuthState(): string | null {
    return isBrowser() ? sessionStorage.getItem(KEYS.authState) : null;
  },
  clearPkce() {
    if (!isBrowser()) return;
    sessionStorage.removeItem(KEYS.pkceVerifier);
    sessionStorage.removeItem(KEYS.authState);
  },
};

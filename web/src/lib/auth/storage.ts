/**
 * sessionStorage helpers for the PKCE round-trip.
 *
 * No tokens are stored on the client — they live server-side, addressed
 * by an opaque httpOnly session cookie. Only the PKCE verifier and state
 * sit here briefly while the browser bounces through the OIDC redirect.
 */

const KEYS = {
  pkceVerifier: "aviary_pkce_verifier",
  authState: "aviary_auth_state",
} as const;

function isBrowser() {
  return typeof window !== "undefined";
}

export const tokenStorage = {
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

import { ApiError, NetworkError, NotFoundError, UnauthorizedError } from "./errors";

/**
 * HTTP client for `/api/*`. Auth flows over an httpOnly session cookie
 * (no Authorization header). On 401 we throw `UnauthorizedError` and
 * leave the redirect decision to the caller — the auth provider treats
 * the first /auth/me 401 as "not signed in" rather than redirecting to
 * Keycloak in a loop.
 */

async function doFetch(path: string, options?: RequestInit): Promise<Response> {
  return fetch(`/api${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await doFetch(path, options);
  } catch (err) {
    throw new NetworkError(err instanceof Error ? err.message : "Network failed");
  }

  if (res.status === 401) {
    throw new UnauthorizedError();
  }

  if (res.status === 404) {
    const body = await res.json().catch(() => ({}));
    throw new NotFoundError(body.detail || "Not found");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || "API error", body);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const http = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T = void>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
};

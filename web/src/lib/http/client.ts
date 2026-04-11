import { ensureValidToken, logout, refreshAccessToken } from "@/lib/auth";
import { ApiError, NetworkError, NotFoundError, UnauthorizedError } from "./errors";

/**
 * HTTP client for `/api/*`. Injects auth token, retries once on 401, throws
 * typed `ApiError` subclasses. Callers must not catch silently.
 */

async function doFetch(path: string, options?: RequestInit): Promise<Response> {
  const token = await ensureValidToken();

  return fetch(`/api${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

  // Try one refresh on 401
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doFetch(path, options);
    }
  }

  if (res.status === 401) {
    await logout();
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

// Convenience helpers — typed wrappers for the common cases
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

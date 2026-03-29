import { ensureValidToken, logout, refreshAccessToken } from "./auth";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function doFetch(path: string, options?: RequestInit): Promise<Response> {
  // Ensure we have a valid (non-expired) token before making the request
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

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  let res = await doFetch(path, options);

  // If 401, attempt one token refresh and retry
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doFetch(path, options);
    }
  }

  // Still 401 after refresh attempt — session is truly expired
  if (res.status === 401) {
    await logout();
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || "API error");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

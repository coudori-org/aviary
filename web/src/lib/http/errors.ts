/**
 * Error taxonomy for API client.
 *
 * Callers should switch on .status (or instanceof) to render appropriate
 * UI rather than checking strings.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UnauthorizedError extends ApiError {
  constructor(message = "Unauthorized") {
    super(401, message);
    this.name = "UnauthorizedError";
  }
}

export class NotFoundError extends ApiError {
  constructor(message = "Not found") {
    super(404, message);
    this.name = "NotFoundError";
  }
}

export class NetworkError extends ApiError {
  constructor(message = "Network error") {
    super(0, message);
    this.name = "NetworkError";
  }
}

/** Extract a user-friendly message from any error. */
export function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

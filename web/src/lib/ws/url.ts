/**
 * WebSocket base URL derived from the page origin. Prod (ALB) and dev
 * (Caddy) both put REST and WS behind one domain, so same-origin is
 * the only mode we support.
 */
export function getWsBaseUrl(): string {
  if (typeof window === "undefined") {
    throw new Error("getWsBaseUrl() called outside the browser");
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

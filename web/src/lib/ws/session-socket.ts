import { ensureValidToken } from "@/lib/auth";
import type { WSMessage } from "./types";

/**
 * Session WebSocket factory. Caller owns reconnect lifecycle.
 */

export interface SessionSocketHandlers {
  onMessage: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (event: Event) => void;
}

function getWsBaseUrl(): string {
  if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL;
  }
  if (typeof window !== "undefined") {
    return `ws://${window.location.hostname}:8000`;
  }
  return "ws://localhost:8000";
}

export async function openSessionSocket(
  sessionId: string,
  handlers: SessionSocketHandlers,
): Promise<WebSocket> {
  const token = await ensureValidToken();
  if (!token) throw new Error("Cannot open WebSocket: no auth token");

  const url = `${getWsBaseUrl()}/api/sessions/${sessionId}/ws?token=${token}`;
  const ws = new WebSocket(url);

  ws.onopen = () => handlers.onOpen?.();
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data) as WSMessage;
    handlers.onMessage(msg);
  };
  ws.onclose = () => handlers.onClose?.();
  ws.onerror = (event) => handlers.onError?.(event);

  return ws;
}

/** Helper for sending typed messages over a session WS. */
export function sendWsMessage(ws: WebSocket | null, msg: object): boolean {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(msg));
  return true;
}

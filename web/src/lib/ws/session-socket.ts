import { getWsBaseUrl } from "./url";
import type { WSMessage } from "./types";

export interface SessionSocketHandlers {
  onMessage: (msg: WSMessage) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (event: Event) => void;
}

export async function openSessionSocket(
  sessionId: string,
  handlers: SessionSocketHandlers,
): Promise<WebSocket> {
  const url = `${getWsBaseUrl()}/api/sessions/${sessionId}/ws`;
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

export function sendWsMessage(ws: WebSocket | null, msg: object): boolean {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(msg));
  return true;
}

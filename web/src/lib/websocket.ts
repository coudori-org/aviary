import { ensureValidToken } from "./auth";

export type ConnectionStatus =
  | "connecting"
  | "provisioning"
  | "spawning"
  | "waiting"
  | "ready"
  | "offline"
  | "disconnected";

export type WSMessage =
  | { type: "status"; status: ConnectionStatus; message?: string }
  | { type: "message"; content: string }
  | { type: "chunk"; content: string }
  | { type: "user_message"; sender_id: string; content: string }
  | { type: "tool_use"; name: string; input: Record<string, unknown>; tool_use_id?: string; parent_tool_use_id?: string }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error?: boolean; parent_tool_use_id?: string }
  | { type: "tool_progress"; tool_use_id: string; tool_name: string; parent_tool_use_id?: string | null; elapsed_time_seconds: number }
  | { type: "thinking"; content: string }
  | { type: "done"; messageId: string }
  | { type: "error"; message: string }
  | { type: "replay_start" }
  | { type: "replay_end" }
  | { type: "stream_complete"; content: string; messageId: string }
  | { type: "cancelled"; messageId?: string };

export async function createSessionWebSocket(
  sessionId: string,
  onMessage: (msg: WSMessage) => void,
  onClose?: () => void
): Promise<WebSocket> {
  // Ensure token is valid before establishing WebSocket connection
  const token = await ensureValidToken();
  const wsUrl =
    process.env.NEXT_PUBLIC_WS_URL || `ws://${window.location.hostname}:8000`;
  const ws = new WebSocket(`${wsUrl}/api/sessions/${sessionId}/ws?token=${token}`);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data) as WSMessage;
      onMessage(msg);
    } catch {
      // Ignore unparseable messages
    }
  };

  ws.onclose = () => {
    onMessage({ type: "status", status: "disconnected" });
    onClose?.();
  };

  return ws;
}

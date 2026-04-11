/**
 * Discriminated union of all WebSocket messages exchanged with the runtime.
 *
 * Server → client and client → server messages share this same union;
 * use `type` to discriminate.
 */

export type ConnectionStatus =
  | "connecting"
  | "provisioning"
  | "spawning"
  | "waiting"
  | "ready"
  | "offline"
  | "disconnected"
  | "reconnecting";

export type WSMessage =
  | { type: "status"; status: ConnectionStatus; message?: string }
  | { type: "message"; content: string }
  | { type: "chunk"; content: string }
  | { type: "user_message"; sender_id: string; content: string }
  | {
      type: "tool_use";
      name: string;
      input: Record<string, unknown>;
      tool_use_id?: string;
      parent_tool_use_id?: string;
    }
  | {
      type: "tool_result";
      tool_use_id: string;
      content: string;
      is_error?: boolean;
      parent_tool_use_id?: string;
    }
  | {
      type: "tool_progress";
      tool_use_id: string;
      tool_name: string;
      parent_tool_use_id?: string | null;
      elapsed_time_seconds: number;
    }
  | { type: "thinking"; content: string }
  | { type: "done"; messageId: string }
  | { type: "error"; message: string; rollback_message_id?: string }
  | { type: "replay_start" }
  | { type: "replay_end" }
  | { type: "stream_complete"; content: string; messageId: string }
  | { type: "cancelled"; messageId?: string };

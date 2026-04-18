import type { SseEventType } from "./sse-events.js";

/**
 * The shape of one SSE event on the wire. Used both by the accumulator
 * (which emits the text/thinking/tool_use subset) and by the runtime
 * server (which additionally emits tool_result/tool_progress/error/result).
 */
export interface SSEChunk {
  type: SseEventType;
  content?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  is_error?: boolean;
  parent_tool_use_id?: string | null;
  tool_name?: string;
  elapsed_time_seconds?: number;
  message?: string;
  session_id?: string;
  duration_ms?: number;
  num_turns?: number;
  total_cost_usd?: number;
  usage?: Record<string, unknown>;
}

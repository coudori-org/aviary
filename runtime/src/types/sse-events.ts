/**
 * Canonical SSE event type names — KEEP IN SYNC with
 * `shared/aviary_shared/sse_events.py` on the Python side.
 *
 * Adding a new type here without adding it there (and vice versa) will
 * produce relay that silently drops the event at one hop.
 */
export type SseEventType =
  | "query_started"   // runtime started the SDK query
  | "stream_started"  // supervisor allocated a stream_id (not from runtime)
  | "chunk"           // text delta
  | "thinking"        // thinking delta
  | "tool_use"        // assistant called a tool
  | "tool_result"     // tool returned
  | "tool_progress"   // long-running tool heartbeat
  | "error"           // terminal — runtime failed mid-stream
  | "result";         // terminal — SDK returned (duration, cost, usage)

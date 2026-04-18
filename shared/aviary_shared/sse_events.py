"""Canonical SSE event type names used across runtime → supervisor → API → UI.

The TS mirror at ``runtime/src/types/sse-events.ts`` MUST stay in sync —
adding a new type here without adding it there (and vice versa) will
produce runtime relay that silently drops the event at one hop.
"""

from __future__ import annotations

from typing import Literal


# Event types the runtime emits. Supervisor relays them verbatim to Redis,
# the chat API forwards them to the WS client, and the UI's block
# renderer discriminates on this union.
SseEventType = Literal[
    "query_started",   # runtime started the SDK query
    "stream_started",  # supervisor allocated a stream_id (not from runtime)
    "chunk",           # text delta
    "thinking",        # thinking delta
    "tool_use",        # assistant called a tool
    "tool_result",     # tool returned
    "tool_progress",   # long-running tool heartbeat
    "error",           # terminal — runtime failed mid-stream
    "result",          # terminal — SDK returned (duration, cost, usage)
]

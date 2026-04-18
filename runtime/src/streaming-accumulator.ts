/**
 * Extracts SSE chunks from the two ways the SDK surfaces content:
 *
 *   1. **stream_event** — Anthropic backends emit content_block_delta
 *      messages with text/thinking deltas. Real-time token-level stream.
 *   2. **assistant snapshots** — ollama/vllm don't emit stream_events;
 *      text/thinking land as cumulative snapshots on the assistant
 *      message. We diff each snapshot against what we've emitted so far,
 *      handling block flushes (content length resets when a new block
 *      starts) as natural resets.
 *
 * `hasStreamDeltas` is set the moment path (1) fires for this accumulator
 * — from then on, snapshot text/thinking are ignored (Anthropic already
 * emitted them). Tool_use blocks come from path (2) on every backend and
 * are de-duplicated by id.
 */

import type { SSEChunk } from "./types/sse-chunk.js";

export class StreamingAccumulator {
  private emittedTextLen = 0;
  private emittedThinkingLen = 0;
  private hasStreamDeltas = false;
  private emittedToolIds = new Set<string>();
  fullResponse = "";

  /** Consume a `stream_event` SDK message. Returns a chunk to emit or null. */
  consumeStreamEvent(event: Record<string, any>): SSEChunk | null {
    if (event.type !== "content_block_delta" || !event.delta) return null;
    if (event.delta.type === "text_delta" && event.delta.text) {
      this.hasStreamDeltas = true;
      const delta = event.delta.text as string;
      this.emittedTextLen += delta.length;
      this.fullResponse += delta;
      return { type: "chunk", content: delta };
    }
    if (event.delta.type === "thinking_delta" && event.delta.thinking) {
      this.hasStreamDeltas = true;
      const delta = event.delta.thinking as string;
      this.emittedThinkingLen += delta.length;
      return { type: "thinking", content: delta };
    }
    return null;
  }

  /** Consume one block from an assistant snapshot. Returns a chunk or null. */
  consumeAssistantBlock(block: Record<string, any>, parentId: string | null): SSEChunk | null {
    if (block.type === "thinking" && !this.hasStreamDeltas) {
      const thinking = (block.thinking ?? "") as string;
      // Block flushing creates multiple short blocks, each with its own
      // cumulative content — detect a new block when content shrinks.
      if (thinking.length < this.emittedThinkingLen) this.emittedThinkingLen = 0;
      if (thinking.length > this.emittedThinkingLen) {
        const delta = thinking.slice(this.emittedThinkingLen);
        this.emittedThinkingLen = thinking.length;
        return { type: "thinking", content: delta };
      }
      return null;
    }
    if (block.type === "text" && !this.hasStreamDeltas) {
      const text = block.text as string;
      if (text.length < this.emittedTextLen) this.emittedTextLen = 0;
      if (text.length > this.emittedTextLen) {
        const delta = text.slice(this.emittedTextLen);
        this.emittedTextLen = text.length;
        this.fullResponse += delta;
        return { type: "chunk", content: delta };
      }
      return null;
    }
    if (block.type === "tool_use") {
      if (this.emittedToolIds.has(block.id)) return null;
      this.emittedToolIds.add(block.id);
      return {
        type: "tool_use",
        name: block.name,
        input: block.input,
        tool_use_id: block.id,
        ...(parentId ? { parent_tool_use_id: parentId } : {}),
      };
    }
    return null;
  }

  /** New assistant turn starts after a tool_result user message —
   *  reset cumulative counters so the next snapshot's text diffs against
   *  an empty baseline. `hasStreamDeltas` is intentionally sticky: once
   *  the backend has emitted real deltas we never fall back to snapshot
   *  diffing for this session. */
  resetForNewTurn(): void {
    this.emittedTextLen = 0;
    this.emittedThinkingLen = 0;
  }
}

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { StreamingAccumulator } from "./streaming-accumulator.js";

describe("StreamingAccumulator", () => {
  describe("consumeStreamEvent (Anthropic delta path)", () => {
    it("emits text_delta as a chunk and accumulates fullResponse", () => {
      const acc = new StreamingAccumulator();
      const out = acc.consumeStreamEvent({
        type: "content_block_delta",
        delta: { type: "text_delta", text: "hello" },
      });
      assert.deepEqual(out, { type: "chunk", content: "hello" });
      assert.equal(acc.fullResponse, "hello");
    });

    it("emits thinking_delta as thinking chunk", () => {
      const acc = new StreamingAccumulator();
      const out = acc.consumeStreamEvent({
        type: "content_block_delta",
        delta: { type: "thinking_delta", thinking: "reasoning" },
      });
      assert.deepEqual(out, { type: "thinking", content: "reasoning" });
    });

    it("ignores non-delta events", () => {
      const acc = new StreamingAccumulator();
      assert.equal(
        acc.consumeStreamEvent({ type: "message_start", message: {} }),
        null,
      );
    });
  });

  describe("consumeAssistantBlock (snapshot diff path)", () => {
    it("diffs cumulative text against emitted baseline", () => {
      const acc = new StreamingAccumulator();
      const first = acc.consumeAssistantBlock({ type: "text", text: "hi" }, null);
      const second = acc.consumeAssistantBlock(
        { type: "text", text: "hi there" },
        null,
      );
      assert.deepEqual(first, { type: "chunk", content: "hi" });
      assert.deepEqual(second, { type: "chunk", content: " there" });
      assert.equal(acc.fullResponse, "hi there");
    });

    it("resets counter when content shrinks (block flush)", () => {
      const acc = new StreamingAccumulator();
      acc.consumeAssistantBlock({ type: "text", text: "first block" }, null);
      // A new block starts — content length drops, treat as fresh baseline.
      const out = acc.consumeAssistantBlock(
        { type: "text", text: "new" },
        null,
      );
      assert.deepEqual(out, { type: "chunk", content: "new" });
    });

    it("suppresses snapshot text once a delta event has fired", () => {
      const acc = new StreamingAccumulator();
      acc.consumeStreamEvent({
        type: "content_block_delta",
        delta: { type: "text_delta", text: "stream" },
      });
      const snapshot = acc.consumeAssistantBlock(
        { type: "text", text: "stream and snapshot" },
        null,
      );
      assert.equal(snapshot, null);
    });

    it("suppresses snapshot thinking once a delta event has fired", () => {
      const acc = new StreamingAccumulator();
      acc.consumeStreamEvent({
        type: "content_block_delta",
        delta: { type: "thinking_delta", thinking: "think" },
      });
      const snapshot = acc.consumeAssistantBlock(
        { type: "thinking", thinking: "think more" },
        null,
      );
      assert.equal(snapshot, null);
    });

    it("de-duplicates tool_use by id", () => {
      const acc = new StreamingAccumulator();
      const first = acc.consumeAssistantBlock(
        { type: "tool_use", id: "t1", name: "Read", input: { path: "/a" } },
        null,
      );
      const second = acc.consumeAssistantBlock(
        { type: "tool_use", id: "t1", name: "Read", input: { path: "/a" } },
        null,
      );
      assert.deepEqual(first, {
        type: "tool_use",
        name: "Read",
        input: { path: "/a" },
        tool_use_id: "t1",
      });
      assert.equal(second, null);
    });

    it("propagates parent_tool_use_id when provided", () => {
      const acc = new StreamingAccumulator();
      const out = acc.consumeAssistantBlock(
        { type: "tool_use", id: "t2", name: "Bash", input: {} },
        "parent-abc",
      );
      assert.deepEqual(out, {
        type: "tool_use",
        name: "Bash",
        input: {},
        tool_use_id: "t2",
        parent_tool_use_id: "parent-abc",
      });
    });
  });

  describe("resetForNewTurn", () => {
    it("resets counters but keeps hasStreamDeltas sticky", () => {
      const acc = new StreamingAccumulator();
      // First turn fires a delta so hasStreamDeltas flips on.
      acc.consumeStreamEvent({
        type: "content_block_delta",
        delta: { type: "text_delta", text: "turn1" },
      });
      acc.resetForNewTurn();
      // Even after reset, snapshot text must still be suppressed because
      // this session has established the delta path.
      const out = acc.consumeAssistantBlock(
        { type: "text", text: "turn2" },
        null,
      );
      assert.equal(out, null);
    });

    it("lets snapshots emit again after reset when no delta has fired", () => {
      const acc = new StreamingAccumulator();
      acc.consumeAssistantBlock({ type: "text", text: "first" }, null);
      acc.resetForNewTurn();
      const out = acc.consumeAssistantBlock(
        { type: "text", text: "second" },
        null,
      );
      assert.deepEqual(out, { type: "chunk", content: "second" });
    });
  });
});

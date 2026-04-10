"""
Monkeypatch: fix Anthropic adapter streaming for non-Anthropic backends.

LiteLLM's experimental Anthropic Messages adapter (/v1/messages -> OpenAI
/v1/chat/completions) has two streaming issues when converting responses
back to Anthropic SSE format:

1. Block type detection: the block type detector only checks `thinking_blocks`
   to identify thinking content, missing `reasoning_content` used by providers
   like Ollama and OpenRouter. This causes thinking_delta events to be emitted
   inside a "text" content block instead of a separate "thinking" block, which
   breaks Claude Code CLI's stream_event forwarding.

2. Dropped trigger delta: when a block transition occurs (e.g. thinking -> text),
   LiteLLM drops the first delta of the new block. This loses the first token.

3. Thinking block flushing: Claude Code CLI emits one `assistant` snapshot per
   completed content block. Without periodic flushing, long thinking blocks
   arrive as a single chunk. This patch injects periodic block stop/start
   events at the SSE byte layer (not touching the iterator's internal state)
   to force intermediate snapshots for real-time thinking streaming.
   Only thinking blocks are flushed — text blocks are left intact because
   internal CLI calls (WebFetch, subagents) expect a single text block and
   would truncate results if text were split across multiple blocks.

4. Tool call special token leak (vLLM/Gemma4): vLLM's Gemma4 tool parser
   leaks special tokens (<|, |>, etc.) into streaming argument deltas,
   producing invalid JSON. Non-streaming is unaffected because vLLM
   post-processes the final output. This patch strips the leaked tokens
   from input_json_delta events. Safe no-op when vLLM fixes this upstream.

Loaded at Python startup via .pth file. Remove when upstream issues are fixed.
"""

import json
import re

# Matches <|\" followed by a word character (thinking-on value start).
_TOKEN_QUOTE_BEFORE_WORD = re.compile(r'<\|\\"(?=\w)')
# Matches "" followed by a word character (leftover from no-thinking cleanup).
_DOUBLE_QUOTE_BEFORE_WORD = re.compile(r'""(?=\w)')


def _clean_tool_json(raw: str) -> str:
    """Strip Gemma4 special token fragments from accumulated tool call JSON.

    vLLM's Gemma4 tool parser leaks ``<|channel>`` / ``<channel|>`` token
    fragments into streaming argument deltas. Two corruption patterns:

    * Thinking ON:  ``<|\\value<|\\"|`` / ``<|\\"value<|\\"``
    * Thinking OFF: ``<|\\"|"value<|\\"|`` (full wrapper around each value)

    Applied only when json.loads() fails, so clean JSON passes through.
    """
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, ValueError):
        pass
    # Step 1: <|\"| (5 chars) — common end-of-value marker
    cleaned = raw.replace('<|\\"|', '')
    # Step 2: <|\" before word char — thinking-on start with leaked quote
    cleaned = _TOKEN_QUOTE_BEFORE_WORD.sub('', cleaned)
    # Step 3: <|\ (3 chars) — remaining token prefixes
    cleaned = cleaned.replace('<|\\', '')
    # Step 4: "" before word char — leftover double quote from no-thinking
    #         pattern where opening <|\"| removal leaves extra "
    cleaned = _DOUBLE_QUOTE_BEFORE_WORD.sub('"', cleaned)
    return cleaned


def _apply():
    from litellm.llms.anthropic.experimental_pass_through.adapters.streaming_iterator import (
        AnthropicStreamWrapper,
    )
    from litellm.llms.anthropic.experimental_pass_through.adapters.transformation import (
        LiteLLMAnthropicMessagesAdapter,
    )

    # ── Fix 1: Block type detection ──────────────────────────────

    _orig_block_detect = (
        LiteLLMAnthropicMessagesAdapter
        ._translate_streaming_openai_chunk_to_anthropic_content_block
    )

    def _patched_block_detect(self, choices):
        from litellm.types.utils import StreamingChoices

        block_type, block_start = _orig_block_detect(self, choices)
        if block_type == "text":
            for choice in choices:
                if isinstance(choice, StreamingChoices) and hasattr(
                    choice.delta, "reasoning_content"
                ):
                    if choice.delta.reasoning_content is not None:
                        from litellm.types.llms.anthropic import (
                            ChatCompletionThinkingBlock,
                        )
                        return "thinking", ChatCompletionThinkingBlock(
                            type="thinking", thinking="", signature=""
                        )
        return block_type, block_start

    LiteLLMAnthropicMessagesAdapter._translate_streaming_openai_chunk_to_anthropic_content_block = (
        _patched_block_detect
    )

    # ── Fix 2: Save trigger delta on block transitions ───────────
    # Also: skip empty chunks (e.g. OpenAI's first role-only chunk) so they
    # don't trigger an empty text block, which would otherwise pollute the
    # SDK's message history and confuse providers like Ollama on the next turn.

    _orig_should_start = AnthropicStreamWrapper._should_start_new_content_block

    def _is_empty_chunk(chunk) -> bool:
        if not chunk.choices:
            return True
        delta = chunk.choices[0].delta
        if delta is None:
            return True
        content = getattr(delta, "content", None)
        if content is not None and len(content) > 0:
            return False
        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls is not None and len(tool_calls) > 0:
            return False
        thinking_blocks = getattr(delta, "thinking_blocks", None)
        if thinking_blocks:
            return False
        reasoning_content = getattr(delta, "reasoning_content", None)
        if reasoning_content is not None and len(reasoning_content) > 0:
            return False
        return True

    def _patched_should_start(self, chunk):
        if _is_empty_chunk(chunk):
            return False
        result = _orig_should_start(self, chunk)
        if result:
            self._trigger_chunk = chunk
        return result

    AnthropicStreamWrapper._should_start_new_content_block = _patched_should_start

    _orig_anext = AnthropicStreamWrapper.__anext__

    async def _patched_anext(self):
        if getattr(self, "_pending_trigger_delta", None) is not None:
            delta = self._pending_trigger_delta
            self._pending_trigger_delta = None
            return delta

        result = await _orig_anext(self)

        if (
            isinstance(result, dict)
            and result.get("type") == "content_block_start"
            and getattr(self, "_trigger_chunk", None) is not None
        ):
            chunk = self._trigger_chunk
            self._trigger_chunk = None
            processed = LiteLLMAnthropicMessagesAdapter().translate_streaming_openai_response_to_anthropic(
                response=chunk,
                current_content_block_index=self.current_content_block_index,
            )
            if processed.get("type") == "content_block_delta":
                self._pending_trigger_delta = processed

        return result

    AnthropicStreamWrapper.__anext__ = _patched_anext

    _orig_next = AnthropicStreamWrapper.__next__

    def _patched_next(self):
        if getattr(self, "_pending_trigger_delta", None) is not None:
            delta = self._pending_trigger_delta
            self._pending_trigger_delta = None
            return delta

        result = _orig_next(self)

        if (
            isinstance(result, dict)
            and result.get("type") == "content_block_start"
            and getattr(self, "_trigger_chunk", None) is not None
        ):
            chunk = self._trigger_chunk
            self._trigger_chunk = None
            processed = LiteLLMAnthropicMessagesAdapter().translate_streaming_openai_response_to_anthropic(
                response=chunk,
                current_content_block_index=self.current_content_block_index,
            )
            if processed.get("type") == "content_block_delta":
                self._pending_trigger_delta = processed

        return result

    AnthropicStreamWrapper.__next__ = _patched_next

    # ── Fix 3: Periodic thinking block flush at the SSE byte layer ─
    # Injects stop/start events into the SSE output WITHOUT touching
    # the streaming iterator's internal state. Rewrites delta indices
    # so they match the virtual block structure.
    # Only thinking_delta is flushed — text blocks are left intact.

    FLUSH_EVERY = 10

    _orig_async_sse = AnthropicStreamWrapper.async_anthropic_sse_wrapper

    def _make_sse(event_type, data):
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n".encode()

    def _flush_tool_buffer(tool_json_buf, block_idx):
        """Clean accumulated tool JSON and emit as a single delta."""
        raw = "".join(tool_json_buf)
        cleaned = _clean_tool_json(raw)
        if cleaned:
            return [_make_sse("content_block_delta", {
                "type": "content_block_delta",
                "index": block_idx,
                "delta": {"type": "input_json_delta", "partial_json": cleaned},
            })]
        return []

    async def _patched_async_sse(self):
        counter = 0
        idx_offset = 0
        tool_json_buf = []    # buffer for input_json_delta partial_json
        tool_block_idx = -1   # index of the current tool_use block

        async for chunk in _orig_async_sse(self):
            if not isinstance(chunk, bytes):
                yield chunk
                continue

            text = chunk.decode("utf-8", errors="replace")
            data_line = None
            for line in text.split("\n"):
                if line.startswith("data: "):
                    data_line = line[6:]
                    break
            if data_line is None:
                yield chunk
                continue

            try:
                d = json.loads(data_line)
            except (json.JSONDecodeError, ValueError):
                yield chunk
                continue

            rtype = d.get("type", "")

            # Apply index offset to all block-related events
            if "index" in d and idx_offset > 0:
                d = {**d, "index": d["index"] + idx_offset}

            if rtype == "content_block_start":
                counter = 0
                cb = d.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tool_block_idx = d.get("index", -1)
                    tool_json_buf = []

            elif rtype == "content_block_stop":
                counter = 0
                stop_idx = d.get("index", -1)
                # Fix 4: flush buffered tool JSON with cleanup before stop
                if stop_idx == tool_block_idx and tool_json_buf:
                    for evt in _flush_tool_buffer(tool_json_buf, tool_block_idx):
                        yield evt
                    tool_json_buf = []
                    tool_block_idx = -1

            elif rtype == "content_block_delta":
                delta_type = d.get("delta", {}).get("type", "")

                # Fix 4: buffer tool call JSON deltas instead of emitting
                if delta_type == "input_json_delta":
                    pj = d.get("delta", {}).get("partial_json", "")
                    tool_json_buf.append(pj)
                    continue  # don't emit yet — flushed at content_block_stop

                # Fix 3: Flush thinking blocks periodically
                if delta_type == "thinking_delta":
                    counter += 1
                    if counter >= FLUSH_EVERY:
                        counter = 0
                        idx = d["index"]
                        new_idx = idx + 1
                        idx_offset += 1

                        yield _make_sse("content_block_delta", d)
                        yield _make_sse("content_block_stop", {
                            "type": "content_block_stop", "index": idx,
                        })
                        yield _make_sse("content_block_start", {
                            "type": "content_block_start",
                            "index": new_idx,
                            "content_block": {"type": "thinking", "thinking": ""},
                        })
                        continue
                else:
                    counter = 0

            event_type = str(d.get("type", "message"))
            yield _make_sse(event_type, d)

    AnthropicStreamWrapper.async_anthropic_sse_wrapper = _patched_async_sse

    # Sync version
    _orig_sync_sse = AnthropicStreamWrapper.anthropic_sse_wrapper

    def _patched_sync_sse(self):
        counter = 0
        idx_offset = 0
        tool_json_buf = []
        tool_block_idx = -1

        for chunk in _orig_sync_sse(self):
            if not isinstance(chunk, bytes):
                yield chunk
                continue

            text = chunk.decode("utf-8", errors="replace")
            data_line = None
            for line in text.split("\n"):
                if line.startswith("data: "):
                    data_line = line[6:]
                    break
            if data_line is None:
                yield chunk
                continue

            try:
                d = json.loads(data_line)
            except (json.JSONDecodeError, ValueError):
                yield chunk
                continue

            rtype = d.get("type", "")

            if "index" in d and idx_offset > 0:
                d = {**d, "index": d["index"] + idx_offset}

            if rtype == "content_block_start":
                counter = 0
                cb = d.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tool_block_idx = d.get("index", -1)
                    tool_json_buf = []

            elif rtype == "content_block_stop":
                counter = 0
                if d.get("index") == tool_block_idx and tool_json_buf:
                    for evt in _flush_tool_buffer(tool_json_buf, tool_block_idx):
                        yield evt
                    tool_json_buf = []
                    tool_block_idx = -1

            elif rtype == "content_block_delta":
                delta_type = d.get("delta", {}).get("type", "")

                if delta_type == "input_json_delta":
                    tool_json_buf.append(d.get("delta", {}).get("partial_json", ""))
                    continue

                if delta_type == "thinking_delta":
                    counter += 1
                    if counter >= FLUSH_EVERY:
                        counter = 0
                        idx = d["index"]
                        new_idx = idx + 1
                        idx_offset += 1

                        yield _make_sse("content_block_delta", d)
                        yield _make_sse("content_block_stop", {
                            "type": "content_block_stop", "index": idx,
                        })
                        yield _make_sse("content_block_start", {
                            "type": "content_block_start",
                            "index": new_idx,
                            "content_block": {"type": "thinking", "thinking": ""},
                        })
                        continue
                else:
                    counter = 0

            event_type = str(d.get("type", "message"))
            yield _make_sse(event_type, d)

    AnthropicStreamWrapper.anthropic_sse_wrapper = _patched_sync_sse


_apply()
del _apply

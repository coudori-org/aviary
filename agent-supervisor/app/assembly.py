"""Reassemble a final agent message from buffered SSE chunks.

The supervisor is the sole assembler. On abort the buffered chunks produce a
partial response; on normal completion they produce the full thing. Either
way the contract is the same: return `(text, blocks)` and merge A2A events.
"""

from __future__ import annotations

from app import redis_client

MAX_TOOL_RESULT_BYTES = 10240


def truncate_tool_result(content: object) -> object:
    if isinstance(content, str) and len(content) > MAX_TOOL_RESULT_BYTES:
        return content[:MAX_TOOL_RESULT_BYTES] + "\n... (truncated)"
    return content


def attach_tool_results(blocks: list[dict], results: dict[str, dict]) -> None:
    for block in blocks:
        tid = block.get("tool_use_id")
        if block.get("type") == "tool_call" and tid and tid in results:
            tr = results[tid]
            block["result"] = tr["content"]
            if tr.get("is_error"):
                block["is_error"] = True


def rebuild_blocks_from_chunks(chunks: list[dict]) -> tuple[str, list[dict]]:
    full_text = ""
    blocks: list[dict] = []
    current_thinking = ""
    current_text = ""
    tool_results: dict[str, dict] = {}

    for chunk in chunks:
        ct = chunk.get("type")
        if ct == "chunk":
            current_text += chunk.get("content", "")
            full_text += chunk.get("content", "")
        elif ct == "thinking":
            current_thinking += chunk.get("content", "")
        elif ct == "tool_use":
            if current_thinking:
                blocks.append({"type": "thinking", "content": current_thinking})
                current_thinking = ""
            if current_text:
                blocks.append({"type": "text", "content": current_text})
                current_text = ""
            tool_block: dict = {
                "type": "tool_call",
                "name": chunk.get("name"),
                "input": chunk.get("input"),
                "tool_use_id": chunk.get("tool_use_id"),
            }
            if chunk.get("parent_tool_use_id"):
                tool_block["parent_tool_use_id"] = chunk["parent_tool_use_id"]
            blocks.append(tool_block)
        elif ct == "tool_result":
            tid = chunk.get("tool_use_id")
            if tid:
                tool_results[tid] = {
                    "content": truncate_tool_result(chunk.get("content", "")),
                    "is_error": chunk.get("is_error", False),
                }

    if current_thinking:
        blocks.append({"type": "thinking", "content": current_thinking})
    if current_text:
        blocks.append({"type": "text", "content": current_text})

    attach_tool_results(blocks, tool_results)
    return full_text, blocks


async def merge_a2a_events(session_id: str, blocks: list[dict]) -> None:
    """Splice sub-agent tool_use/tool_result events (emitted to Redis by the
    A2A helper on the runtime side) into the parent block list in-place."""
    extra: list[dict] = []
    extra_results: dict[str, dict] = {}

    for block in list(blocks):
        if (
            block.get("type") == "tool_call"
            and block.get("name", "").startswith("mcp__a2a__ask_")
        ):
            tool_use_id = block.get("tool_use_id")
            if not tool_use_id:
                continue
            events = await redis_client.get_a2a_events(session_id, tool_use_id)
            for evt in events:
                if evt.get("type") == "tool_use":
                    extra.append({
                        "type": "tool_call",
                        "name": evt.get("name"),
                        "input": evt.get("input", {}),
                        "tool_use_id": evt.get("tool_use_id"),
                        "parent_tool_use_id": evt.get("parent_tool_use_id"),
                    })
                elif evt.get("type") == "tool_result":
                    tid = evt.get("tool_use_id")
                    if tid:
                        extra_results[tid] = {
                            "content": evt.get("content", ""),
                            "is_error": evt.get("is_error", False),
                        }
            await redis_client.clear_a2a_events(session_id, tool_use_id)

    if extra:
        blocks.extend(extra)
        attach_tool_results(extra, extra_results)

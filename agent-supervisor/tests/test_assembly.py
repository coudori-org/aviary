"""Assembly: rebuild_blocks_from_chunks + merge_a2a_events edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app import assembly


def test_rebuild_groups_text_thinking_tool_in_order():
    chunks = [
        {"type": "thinking", "content": "I need to read"},
        {"type": "chunk", "content": "let me check "},
        {"type": "tool_use", "name": "Read", "input": {"path": "/x"}, "tool_use_id": "t1"},
        {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
        {"type": "chunk", "content": "done"},
    ]
    text, blocks = assembly.rebuild_blocks_from_chunks(chunks)
    assert text == "let me check done"
    assert [b["type"] for b in blocks] == ["thinking", "text", "tool_call", "text"]
    tool_block = blocks[2]
    assert tool_block["result"] == "ok"
    assert tool_block["tool_use_id"] == "t1"


def test_tool_result_is_truncated_when_huge():
    big = "x" * (assembly.MAX_TOOL_RESULT_BYTES + 100)
    chunks = [
        {"type": "tool_use", "name": "Bash", "input": {}, "tool_use_id": "t1"},
        {"type": "tool_result", "tool_use_id": "t1", "content": big},
    ]
    _, blocks = assembly.rebuild_blocks_from_chunks(chunks)
    result = blocks[0]["result"]
    assert result.endswith("... (truncated)")
    assert len(result) < len(big)


def test_rebuild_ignores_whitespace_only_text_block():
    chunks = [
        {"type": "chunk", "content": "   "},
        {"type": "tool_use", "name": "Read", "input": {}, "tool_use_id": "t1"},
    ]
    _, blocks = assembly.rebuild_blocks_from_chunks(chunks)
    assert [b["type"] for b in blocks] == ["tool_call"]


def test_parent_tool_use_id_propagates_to_block():
    chunks = [
        {
            "type": "tool_use",
            "name": "Write",
            "input": {},
            "tool_use_id": "child",
            "parent_tool_use_id": "parent-xyz",
        },
    ]
    _, blocks = assembly.rebuild_blocks_from_chunks(chunks)
    assert blocks[0]["parent_tool_use_id"] == "parent-xyz"


@pytest.mark.asyncio
async def test_merge_a2a_splices_sub_agent_events_under_parent():
    blocks: list[dict] = [
        {
            "type": "tool_call",
            "name": "mcp__a2a__ask_planner",
            "input": {"q": "plan"},
            "tool_use_id": "parent-1",
        },
    ]
    sub_events = [
        {"type": "tool_use", "name": "Read", "input": {"path": "/p"}, "tool_use_id": "c1", "parent_tool_use_id": "parent-1"},
        {"type": "tool_result", "tool_use_id": "c1", "content": "planner says"},
    ]
    with (
        patch("app.redis_client.get_a2a_events", new_callable=AsyncMock, return_value=sub_events),
        patch("app.redis_client.clear_a2a_events", new_callable=AsyncMock) as clear,
    ):
        await assembly.merge_a2a_events("session-1", blocks)

    clear.assert_awaited_once_with("session-1", "parent-1")
    child = [b for b in blocks if b.get("tool_use_id") == "c1"]
    assert len(child) == 1
    assert child[0]["parent_tool_use_id"] == "parent-1"
    assert child[0]["result"] == "planner says"


@pytest.mark.asyncio
async def test_merge_a2a_no_parent_blocks_is_noop():
    blocks: list[dict] = [
        {"type": "text", "content": "just text"},
        {"type": "tool_call", "name": "Read", "input": {}, "tool_use_id": "t1"},
    ]
    with (
        patch("app.redis_client.get_a2a_events", new_callable=AsyncMock) as get_ev,
        patch("app.redis_client.clear_a2a_events", new_callable=AsyncMock) as clear,
    ):
        await assembly.merge_a2a_events("session-1", blocks)

    get_ev.assert_not_awaited()
    clear.assert_not_awaited()
    assert len(blocks) == 2


@pytest.mark.asyncio
async def test_merge_a2a_ignores_parent_block_without_tool_use_id():
    blocks: list[dict] = [
        {
            "type": "tool_call",
            "name": "mcp__a2a__ask_planner",
            "input": {},
            # tool_use_id intentionally missing
        },
    ]
    with (
        patch("app.redis_client.get_a2a_events", new_callable=AsyncMock) as get_ev,
        patch("app.redis_client.clear_a2a_events", new_callable=AsyncMock),
    ):
        await assembly.merge_a2a_events("session-1", blocks)

    get_ev.assert_not_awaited()

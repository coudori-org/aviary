"""A2A (Agent-to-Agent) event merging for sub-agent tool calls."""

from app.services import redis_service
from app.services.stream.blocks import attach_tool_results


async def merge_a2a_events(session_id: str, blocks: list[dict]) -> None:
    """Fetch sub-agent tool_use/tool_result events from Redis, normalize to
    blocks_meta format, append to blocks, and attach results. In-place."""
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
            events = await redis_service.get_a2a_events(session_id, tool_use_id)
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
            await redis_service.clear_a2a_events(session_id, tool_use_id)

    if extra:
        blocks.extend(extra)
        attach_tool_results(extra, extra_results)

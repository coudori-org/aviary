"""Conversation history manager — persists to /workspace/sessions/{session_id}/.history/."""

import json
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path("/workspace/sessions")


def _history_dir(session_id: str) -> Path:
    return WORKSPACE_ROOT / session_id / ".history"


def _messages_file(session_id: str) -> Path:
    return _history_dir(session_id) / "messages.jsonl"


def ensure_history_dir(session_id: str):
    _history_dir(session_id).mkdir(parents=True, exist_ok=True)


def load_messages(session_id: str) -> list[dict[str, Any]]:
    """Load all messages from the JSONL history file."""
    messages_file = _messages_file(session_id)
    if not messages_file.exists():
        return []
    messages = []
    with open(messages_file) as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages


def append_message(session_id: str, role: str, content: str, metadata: dict | None = None):
    """Append a message to the history file."""
    ensure_history_dir(session_id)
    entry = {"role": role, "content": content}
    if metadata:
        entry["metadata"] = metadata
    with open(_messages_file(session_id), "a") as f:
        f.write(json.dumps(entry) + "\n")


def get_conversation_for_sdk(session_id: str) -> list[dict[str, str]]:
    """Format conversation history for Claude Agent SDK."""
    messages = load_messages(session_id)
    return [{"role": m["role"], "content": m["content"]} for m in messages]

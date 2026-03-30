"""Session manager for multi-session runtime Pod.

Tracks active sessions, enforces concurrency limits, and provides
per-session message serialization via asyncio locks.
"""

import asyncio
import enum
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("/workspace/sessions")
MAX_CONCURRENT_SESSIONS = int(os.environ.get("MAX_CONCURRENT_SESSIONS", "10"))


class SessionState(str, enum.Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    ERROR = "error"


@dataclass
class SessionEntry:
    session_id: str
    state: SessionState = SessionState.IDLE
    workspace: Path = field(init=False)
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self):
        self.workspace = WORKSPACE_ROOT / self.session_id


class SessionManager:
    """Track and manage active sessions within this Pod."""

    def __init__(self, max_sessions: int = MAX_CONCURRENT_SESSIONS):
        self._sessions: dict[str, SessionEntry] = {}
        self._max_sessions = max_sessions
        self._lock = asyncio.Lock()  # protects _sessions dict mutations

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    @property
    def streaming_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.state == SessionState.STREAMING)

    @property
    def has_capacity(self) -> bool:
        return self.active_count < self._max_sessions

    async def get_or_create(self, session_id: str) -> SessionEntry:
        """Get existing session or register a new one. Raises if at capacity."""
        async with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]
            if not self.has_capacity:
                raise RuntimeError(f"Pod at capacity ({self._max_sessions} sessions)")
            entry = SessionEntry(session_id=session_id)
            entry.workspace.mkdir(parents=True, exist_ok=True)
            self._sessions[session_id] = entry
            return entry

    def get(self, session_id: str) -> SessionEntry | None:
        return self._sessions.get(session_id)

    async def remove(self, session_id: str, cleanup_files: bool = True) -> bool:
        """Remove session and optionally delete workspace files."""
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
            if entry is None:
                return False
        if cleanup_files and entry.workspace.exists():
            shutil.rmtree(entry.workspace, ignore_errors=True)
        return True

    def list_sessions(self) -> list[dict]:
        return [
            {
                "session_id": e.session_id,
                "state": e.state.value,
                "created_at": e.created_at,
                "last_active_at": e.last_active_at,
            }
            for e in self._sessions.values()
        ]

    async def graceful_shutdown(self, timeout: float = 30.0):
        """Wait for all streaming sessions to finish, up to timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.streaming_count == 0:
                return
            await asyncio.sleep(0.5)
        logger.warning("Shutdown timeout: %d sessions still streaming", self.streaming_count)

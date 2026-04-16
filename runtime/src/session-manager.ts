/**
 * Session registry + per-(session, agent) mutex for the agent runtime.
 *
 * No concurrency cap — scaling is an infra-level concern. The runtime accepts
 * every request it receives.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import {
  WORKSPACE_ROOT,
  sessionClaudeDir,
  sessionSharedDir,
  sessionTmp,
  sessionVenvDir,
} from "./constants.js";

export { WORKSPACE_ROOT };

export interface SessionEntry {
  sessionId: string;
  agentId: string;
  sharedDir: string;
  createdAt: number;
  /** Simple mutex: resolves when the lock is released. */
  _lock: {
    acquire(): Promise<() => void>;
  };
}

function createMutex() {
  let _queue: Array<() => void> = [];
  let _locked = false;

  return {
    acquire(): Promise<() => void> {
      return new Promise<() => void>((resolve) => {
        const tryAcquire = () => {
          if (!_locked) {
            _locked = true;
            resolve(() => {
              _locked = false;
              const next = _queue.shift();
              if (next) next();
            });
          } else {
            _queue.push(tryAcquire);
          }
        };
        tryAcquire();
      });
    },
  };
}

function entryKey(sessionId: string, agentId: string): string {
  return `${sessionId}/${agentId}`;
}

export class SessionManager {
  private _sessions = new Map<string, SessionEntry>();

  get activeCount(): number {
    return this._sessions.size;
  }

  getOrCreate(sessionId: string, agentId: string): SessionEntry {
    const key = entryKey(sessionId, agentId);
    const existing = this._sessions.get(key);
    if (existing) return existing;

    const shared = sessionSharedDir(sessionId);
    fs.mkdirSync(shared, { recursive: true });
    fs.mkdirSync(sessionClaudeDir(sessionId, agentId), { recursive: true });
    fs.mkdirSync(sessionTmp(sessionId, agentId), { recursive: true });
    // venv parent only — claude-sandbox.sh creates the venv itself.
    fs.mkdirSync(path.dirname(sessionVenvDir(sessionId, agentId)), { recursive: true });

    const entry: SessionEntry = {
      sessionId,
      agentId,
      sharedDir: shared,
      createdAt: Date.now() / 1000,
      _lock: createMutex(),
    };
    this._sessions.set(key, entry);
    return entry;
  }

  get(sessionId: string, agentId: string): SessionEntry | undefined {
    return this._sessions.get(entryKey(sessionId, agentId));
  }

  remove(sessionId: string, agentId: string, cleanupFiles = false): boolean {
    const key = entryKey(sessionId, agentId);
    const entry = this._sessions.get(key);
    if (!entry) return false;
    this._sessions.delete(key);
    if (cleanupFiles) {
      const claude = sessionClaudeDir(sessionId, agentId);
      const venv = sessionVenvDir(sessionId, agentId);
      const tmp = sessionTmp(sessionId, agentId);
      for (const p of [claude, venv, tmp]) {
        if (fs.existsSync(p)) {
          fs.rmSync(p, { recursive: true, force: true });
        }
      }
    }
    return true;
  }

  listSessions(): Array<{ session_id: string; agent_id: string; created_at: number }> {
    return Array.from(this._sessions.values()).map((e) => ({
      session_id: e.sessionId,
      agent_id: e.agentId,
      created_at: e.createdAt,
    }));
  }

  async gracefulShutdown(timeout = 30_000): Promise<void> {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      if (this.activeCount === 0) return;
      await new Promise((r) => setTimeout(r, 500));
    }
    console.warn(
      `Shutdown timeout: ${this.activeCount} sessions still active`,
    );
  }
}

// Mount points are coordinated with scripts/claude-sandbox.sh and
// agent-supervisor/app/backends/k3s/manifests.py — keep them in sync.

import * as path from "node:path";

export const WORKSPACE_ROOT = "/workspace";
export const SHARED_WORKSPACE_ROOT = "/workspace-shared";

export function sessionHome(sessionId: string): string {
  return path.join(SHARED_WORKSPACE_ROOT, sessionId);
}

export function sessionClaudeDir(sessionId: string): string {
  return path.join(WORKSPACE_ROOT, ".claude", sessionId);
}

export function sessionVenvDir(sessionId: string): string {
  return path.join(WORKSPACE_ROOT, ".venvs", sessionId);
}

export function sessionTmp(sessionId: string): string {
  return `/tmp/${sessionId}`;
}

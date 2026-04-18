// Pod-side paths (host view). The bwrap sandbox remaps these onto /workspace
// and /workspace/.claude/.venv inside the sandbox — see scripts/claude-sandbox.sh.
//
// The single RWX PVC is mounted at WORKSPACE_ROOT. Every agent/session in the
// environment shares this volume, so isolation is done via path keying plus
// bwrap bind mounts.

import * as path from "node:path";

// Pod mount point of the shared environment PVC.
export const WORKSPACE_ROOT = "/workspace-root";

// SDK runs inside bwrap where the session's shared dir is mounted at /workspace.
export const SANDBOX_WORKSPACE = "/workspace";

/** Per-session shared directory — visible to every agent participating in the session. */
export function sessionSharedDir(sessionId: string): string {
  return path.join(WORKSPACE_ROOT, "sessions", sessionId, "shared");
}

/** Per-(agent, session) CLI context (Claude Code projects, history). */
export function sessionClaudeDir(sessionId: string, agentId: string): string {
  return path.join(WORKSPACE_ROOT, "sessions", sessionId, "agents", agentId, ".claude");
}

/** Per-(agent, session) Python venv overlay. */
export function sessionVenvDir(sessionId: string, agentId: string): string {
  return path.join(WORKSPACE_ROOT, "sessions", sessionId, "agents", agentId, ".venv");
}

/** Per-(agent, session) tmp directory on the pod's local filesystem. */
export function sessionTmp(sessionId: string, agentId: string): string {
  return `/tmp/${agentId}_${sessionId}`;
}

/** Top of a workflow run's artifact tree. Keyed by root_run_id so a resume
 *  chain shares one tree. Agents see this as `/artifacts` (ro) inside the
 *  sandbox when `SESSION_ARTIFACTS_DIR` is set. */
export function workflowArtifactsDir(rootRunId: string): string {
  return path.join(WORKSPACE_ROOT, "workflows", rootRunId, "artifacts");
}

/** Target path for one artifact from one node. */
export function workflowArtifactPath(
  rootRunId: string,
  nodeId: string,
  artifactName: string,
): string {
  return path.join(workflowArtifactsDir(rootRunId), nodeId, artifactName);
}

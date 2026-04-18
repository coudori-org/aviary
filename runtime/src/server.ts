/**
 * Agent Runtime HTTP server — multi-agent, multi-session server that processes
 * messages via Claude Agent SDK (TypeScript).
 *
 * The runtime is agent-agnostic: every request carries its own agent_config
 * (including agent_id) in the body. Sessions are keyed by (session_id, agent_id)
 * and serialized via per-key mutex. Filesystem isolation is enforced by the
 * single-PVC + bubblewrap layout (see scripts/claude-sandbox.sh).
 */

import * as fs from "node:fs";
import express from "express";
import { SessionManager } from "./session-manager.js";
import { WORKSPACE_ROOT, workflowArtifactsDir } from "./constants.js";
import { healthRouter, setReady } from "./health.js";
import { processMessage } from "./agent.js";

const app = express();
app.use(express.json({ limit: "50mb" }));
app.use(healthRouter);

const manager = new SessionManager();

// Track active AbortControllers per (session_id, agent_id) for cancellation.
const activeAbortControllers = new Map<string, AbortController>();
const abortKey = (sessionId: string, agentId: string) => `${sessionId}/${agentId}`;

// Startup
fs.mkdirSync(WORKSPACE_ROOT, { recursive: true });
setReady(true);

interface ContentPart {
  text?: string;
  attachments?: Array<{ type: string; media_type: string; data: string }>;
}

interface AgentConfigBody {
  agent_id?: string;
  model_config?: Record<string, unknown> | null;
  [key: string]: unknown;
}

interface StructuredOutputField {
  name: string;
  type: "str" | "list";
  description?: string;
}

interface StructuredOutputConfig {
  name: string;
  description?: string;
  fields: StructuredOutputField[];
}

interface MessageRequestBody {
  content_parts: ContentPart[];
  session_id: string;
  agent_config: AgentConfigBody;
  output_format?: { type: "json_schema"; schema: Record<string, unknown> };
  // Dynamically-registered in-process MCP tools. Each entry becomes one
  // tool on the `aviary_output` server. The runtime binds them and lets
  // the CLI emit calls as regular `tool_use` events — the caller owns
  // deciding when/why a tool should fire via its own system prompt.
  structured_outputs?: StructuredOutputConfig[];
}

app.post("/message", async (req, res) => {
  const body = req.body as MessageRequestBody;
  const agentId = body.agent_config?.agent_id;

  if (!body.content_parts?.length || !body.session_id || !agentId) {
    res.status(400).json({
      error: "content_parts, session_id, and agent_config.agent_id are required",
    });
    return;
  }

  const entry = manager.getOrCreate(body.session_id, agentId);

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("X-Accel-Buffering", "no");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();

  const release = await entry._lock.acquire();

  const abortController = new AbortController();
  const aKey = abortKey(body.session_id, agentId);
  activeAbortControllers.set(aKey, abortController);

  // `res.on("close")` — not `req.on("close")` — is the reliable signal for
  // client disconnect on a streaming response in Node/Express. `req.on("close")`
  // doesn't fire for in-flight streamed responses, which is why a previous
  // version of this handler missed supervisor aborts entirely.
  res.on("close", () => {
    if (!abortController.signal.aborted) {
      abortController.abort();
    }
  });

  try {
    for await (const chunk of processMessage(
      body.session_id,
      body.content_parts,
      body.agent_config as any,
      abortController,
      body.output_format,
      body.structured_outputs,
    )) {
      if (res.writableEnded || abortController.signal.aborted) break;
      res.write(`data: ${JSON.stringify(chunk)}\n\n`);
    }
  } finally {
    activeAbortControllers.delete(aKey);
    release();
    manager.remove(body.session_id, agentId, false);
  }

  if (!res.writableEnded) {
    res.end();
  }
});

app.post("/abort/:sessionId", (req, res) => {
  const { sessionId } = req.params;
  const agentId = (req.body?.agent_id as string | undefined) ?? undefined;

  if (agentId) {
    const aKey = abortKey(sessionId, agentId);
    const controller = activeAbortControllers.get(aKey);
    if (!controller) {
      res.status(404).json({ error: "No active stream for this session/agent" });
      return;
    }
    controller.abort();
    activeAbortControllers.delete(aKey);
    res.json({ status: "aborted", session_id: sessionId, agent_id: agentId });
    return;
  }

  // No agent_id provided — abort every active stream for this session.
  const aborted: string[] = [];
  for (const key of Array.from(activeAbortControllers.keys())) {
    if (key.startsWith(`${sessionId}/`)) {
      activeAbortControllers.get(key)!.abort();
      activeAbortControllers.delete(key);
      aborted.push(key.slice(sessionId.length + 1));
    }
  }
  if (!aborted.length) {
    res.status(404).json({ error: "No active streams for this session" });
    return;
  }
  res.json({ status: "aborted", session_id: sessionId, agent_ids: aborted });
});

app.get("/sessions", (_req, res) => {
  res.json({
    sessions: manager.listSessions(),
    active: manager.activeCount,
  });
});

app.delete("/sessions/:sessionId", (req, res) => {
  const agentId = (req.query.agent_id as string | undefined) ?? (req.body?.agent_id as string | undefined);
  if (!agentId) {
    res.status(400).json({ error: "agent_id is required (query or body)" });
    return;
  }
  const removed = manager.remove(req.params.sessionId, agentId, true);
  if (!removed) {
    res.status(404).json({ error: "session not found" });
    return;
  }
  res.json({ status: "removed" });
});

app.delete("/workflows/:rootRunId/artifacts", (req, res) => {
  const { rootRunId } = req.params;
  // rootRunId arrives from the supervisor which already validated it's a
  // UUID-shaped string; keep a belt-and-suspenders check so a stray slash
  // or traversal can't reach outside the workflows tree.
  if (!/^[A-Za-z0-9_-]+$/.test(rootRunId)) {
    res.status(400).json({ error: "invalid root_run_id" });
    return;
  }
  const target = workflowArtifactsDir(rootRunId);
  if (!fs.existsSync(target)) {
    res.status(404).json({ error: "artifacts not found" });
    return;
  }
  fs.rmSync(target, { recursive: true, force: true });
  res.json({ status: "removed" });
});

app.get("/metrics", (_req, res) => {
  res.json({
    sessions_active: manager.activeCount,
    sessions_streaming: manager.activeCount,
  });
});

app.post("/shutdown", (_req, res) => {
  setReady(false);
  res.json({
    status: "shutting_down",
    streaming_sessions: manager.activeCount,
  });
});

const PORT = parseInt(process.env.PORT ?? "3000", 10);
const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(`Aviary Runtime listening on :${PORT}`);
});

// Graceful shutdown — drain in-flight sessions before exit. Pod spec sets
// terminationGracePeriodSeconds=600; we wait up to 570s, leaving 30s buffer.
const GRACEFUL_SHUTDOWN_MS = 570_000;
for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, async () => {
    console.log(`Received ${signal}, draining ${manager.activeCount} session(s)...`);
    setReady(false);
    server.close();
    await manager.gracefulShutdown(GRACEFUL_SHUTDOWN_MS);
    process.exit(0);
  });
}

/**
 * Agent runner using the official @anthropic-ai/claude-agent-sdk (TypeScript).
 *
 * All inference is routed through the Inference Router:
 *   claude-agent-sdk -> Claude Code CLI -> Anthropic SDK
 *     -> POST http://inference-router.platform.svc:8080/v1/messages
 *     -> Router inspects model name -> proxies to correct backend
 *
 * Multi-turn conversation is maintained via the SDK's session management:
 *   - Aviary session_id is passed directly as CLI session_id
 *   - CLI stores conversation history at <workspace>/.claude/projects/...
 *   - Pod restart with same PVC: resume=<session_id> restores conversation
 *
 * Session isolation: each claude-agent-sdk subprocess runs inside a bubblewrap
 * sandbox where only its own workspace directory is visible. Other sessions'
 * directories don't exist in the mount namespace. See scripts/claude-sandbox.sh.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { execSync } from "node:child_process";
import { query, type SDKMessage } from "@anthropic-ai/claude-agent-sdk";

const CONFIG_DIR = "/agent/config";
const WORKSPACE_ROOT = "/workspace/sessions";

const INFERENCE_ROUTER_URL =
  process.env.INFERENCE_ROUTER_URL ??
  "http://inference-router.platform.svc:8080";

// Force SDK to use our bwrap wrapper instead of its bundled binary.
// TS SDK option is `pathToClaudeCodeExecutable` (not `cliPath` like Python).
const CLAUDE_CLI_PATH = "/usr/local/bin/claude";

// Model tier env vars — all remapped to agent's configured model so CLI
// internal tasks (WebFetch summarization, subagents) route through inference router
const MODEL_TIER_KEYS = [
  "ANTHROPIC_MODEL",
  "ANTHROPIC_SMALL_FAST_MODEL",
  "ANTHROPIC_DEFAULT_HAIKU_MODEL",
  "ANTHROPIC_DEFAULT_SONNET_MODEL",
  "ANTHROPIC_DEFAULT_OPUS_MODEL",
  "CLAUDE_CODE_SUBAGENT_MODEL",
] as const;

// Pass-through env vars — must be explicit because SDK env dict replaces parent env.
// PATH is required for the subprocess to find `node` and `claude` binaries.
const PASSTHROUGH_KEYS = ["PATH", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "NODE_OPTIONS"] as const;

function sessionWorkspace(sessionId: string): string {
  return path.join(WORKSPACE_ROOT, sessionId);
}

interface AgentConfig {
  instruction?: string;
  tools?: string[];
  policy?: Record<string, unknown>;
  mcp_servers?: Record<string, unknown>;
}

interface ModelConfig {
  model?: string;
  backend?: string;
}

export function loadAgentConfig(): AgentConfig {
  const config: AgentConfig = {};

  const files: Array<[keyof AgentConfig, string, boolean]> = [
    ["instruction", "instruction.md", false],
    ["tools", "tools.json", true],
    ["policy", "policy.json", true],
    ["mcp_servers", "mcp-servers.json", true],
  ];

  for (const [key, filename, isJson] of files) {
    const filePath = path.join(CONFIG_DIR, filename);
    if (fs.existsSync(filePath)) {
      const content = fs.readFileSync(filePath, "utf-8");
      (config as any)[key] = isJson ? JSON.parse(content) : content;
    }
  }

  return config;
}

function hasSessionHistory(workspace: string, sessionId: string): boolean {
  const projectsDir = path.join(workspace, ".claude", "projects");
  if (!fs.existsSync(projectsDir)) return false;

  try {
    for (const d of fs.readdirSync(projectsDir)) {
      if (fs.existsSync(path.join(projectsDir, d, `${sessionId}.jsonl`))) {
        return true;
      }
    }
  } catch {
    // directory not readable
  }
  return false;
}

export interface SSEChunk {
  type: "chunk" | "tool_use" | "tool_result" | "tool_progress" | "result";
  content?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  // tool_progress fields
  tool_name?: string;
  parent_tool_use_id?: string | null;
  elapsed_time_seconds?: number;
  // Result metadata (only on type: "result")
  session_id?: string;
  duration_ms?: number;
  num_turns?: number;
  total_cost_usd?: number;
  usage?: Record<string, unknown>;
}

/**
 * Process a user message through claude-agent-sdk.
 *
 * Agent config is received from the API server (sourced from DB) on every
 * message, ensuring edits to instruction/tools take effect immediately
 * without Pod restart. Falls back to ConfigMap if not provided.
 *
 * Yields SSE-formatted objects:
 *   {type: "chunk", content: "..."}
 *   {type: "tool_use", name: "...", input: {...}, tool_use_id: "..."}
 *   {type: "tool_result", tool_use_id: "...", content: "..."}
 *   {type: "tool_progress", tool_use_id, tool_name, parent_tool_use_id, elapsed_time_seconds}
 *   {type: "result", session_id, duration_ms, num_turns, total_cost_usd, usage}
 */
export async function* processMessage(
  sessionId: string,
  content: string,
  modelConfig?: ModelConfig | null,
  agentConfigFromApi?: AgentConfig | null,
  abortController?: AbortController,
): AsyncGenerator<SSEChunk> {
  const workspace = sessionWorkspace(sessionId);
  fs.mkdirSync(workspace, { recursive: true });

  // Ensure workspace is a git repo with at least one commit —
  // required for subagent worktree isolation (git worktree needs a valid HEAD).
  const gitDir = path.join(workspace, ".git");
  if (!fs.existsSync(gitDir)) {
    execSync(
      'git init -q && git -c user.name=aviary -c user.email=aviary@local commit --allow-empty -q -m "init"',
      { cwd: workspace },
    );
  } else {
    // .git exists but may lack commits (from a previous incomplete init)
    try {
      execSync("git rev-parse HEAD", { cwd: workspace, stdio: "ignore" });
    } catch {
      execSync(
        'git -c user.name=aviary -c user.email=aviary@local commit --allow-empty -q -m "init"',
        { cwd: workspace },
      );
    }
  }

  const agentConfig = agentConfigFromApi ?? loadAgentConfig();
  const mc: ModelConfig = modelConfig ?? { backend: "claude", model: "default" };
  const model = mc.model ?? "default";
  const backend = mc.backend ?? "claude";
  const canResume = hasSessionHistory(workspace, sessionId);

  const env: Record<string, string> = {
    ANTHROPIC_BASE_URL: INFERENCE_ROUTER_URL,
    ANTHROPIC_API_KEY: "routed-via-inference-router",
    ANTHROPIC_CUSTOM_HEADERS: `X-Backend: ${backend}`,
    SESSION_WORKSPACE: workspace,
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    ...Object.fromEntries(MODEL_TIER_KEYS.map((k) => [k, model])),
    ...Object.fromEntries(
      PASSTHROUGH_KEYS.filter((k) => process.env[k]).map((k) => [k, process.env[k]!]),
    ),
  };

  const options = {
    model,
    systemPrompt: agentConfig.instruction,
    cwd: workspace,
    pathToClaudeCodeExecutable: CLAUDE_CLI_PATH,
    permissionMode: "bypassPermissions" as const,
    allowedTools: agentConfig.tools,
    mcpServers: agentConfig.mcp_servers as Record<string, any> | undefined,
    env,
    // TS SDK doesn't expose sessionId as an option, but CLI supports --session-id.
    // Use extraArgs to inject it on first message, resume on subsequent messages.
    ...(canResume ? {} : { extraArgs: { "session-id": sessionId } }),
    ...(canResume ? { resume: sessionId } : {}),
    ...(abortController ? { abortController } : {}),
  };

  let fullResponse = "";

  try {
    for await (const message of query({ prompt: content, options })) {
      const msg = message as SDKMessage & Record<string, any>;

      if (msg.type === "assistant" && msg.message?.content) {
        for (const block of msg.message.content) {
          if (block.type === "text") {
            fullResponse += block.text;
            yield { type: "chunk", content: block.text };
          } else if (block.type === "tool_use") {
            yield { type: "tool_use", name: block.name, input: block.input, tool_use_id: block.id };
          }
        }
      } else if (msg.type === "user" && msg.message?.content) {
        // SDKUserMessage — tool results sent back to the model after execution.
        const content = msg.message.content;
        if (Array.isArray(content)) {
          for (const block of content) {
            if (block.type === "tool_result") {
              yield {
                type: "tool_result",
                tool_use_id: block.tool_use_id,
                content:
                  typeof block.content === "string"
                    ? block.content
                    : JSON.stringify(block.content ?? ""),
              };
            }
          }
        }
      } else if (msg.type === "tool_progress") {
        yield {
          type: "tool_progress",
          tool_use_id: msg.tool_use_id,
          tool_name: msg.tool_name,
          parent_tool_use_id: msg.parent_tool_use_id,
          elapsed_time_seconds: msg.elapsed_time_seconds,
        };
      } else if (msg.type === "result") {
        // Emit final text if nothing was streamed
        if (msg.result && !fullResponse) {
          fullResponse = msg.result;
          yield { type: "chunk", content: msg.result };
        }
        // Emit result metadata (cost, usage, duration)
        yield {
          type: "result",
          session_id: msg.session_id,
          duration_ms: msg.duration_ms,
          num_turns: msg.num_turns,
          total_cost_usd: msg.total_cost_usd,
          usage: msg.usage,
        };
      }
    }
  } catch (e) {
    if (abortController?.signal.aborted) {
      yield { type: "chunk", content: "[Cancelled by user]" };
      return;
    }
    const errorMsg = `[${backend}/${model}] Error: ${e}`;
    yield { type: "chunk", content: errorMsg };
  }
}

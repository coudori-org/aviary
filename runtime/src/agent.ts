/**
 * Agent runner using the official @anthropic-ai/claude-agent-sdk (TypeScript).
 *
 * All inference is routed through LiteLLM:
 *   claude-agent-sdk -> Claude Code CLI -> Anthropic SDK
 *     -> POST http://litellm.platform.svc:4000/v1/messages
 *     -> LiteLLM routes by model name prefix (anthropic/, ollama/, vllm/, bedrock/)
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

import { query, type SDKMessage } from "@anthropic-ai/claude-agent-sdk";
import { startA2AServer, type AccessibleAgent, type A2AServer } from "./a2a-tools.js";
import {
  WORKSPACE_ROOT,
  sessionClaudeDir,
  sessionHome,
  sessionTmp,
  sessionVenvDir,
} from "./constants.js";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Required environment variable ${name} is not set`);
  }
  return value;
}

const LITELLM_URL = requireEnv("INFERENCE_ROUTER_URL");
const LITELLM_API_KEY = requireEnv("LITELLM_API_KEY");

// Force SDK to use our bwrap wrapper instead of its bundled binary.
const CLAUDE_CLI_PATH = "/usr/local/bin/claude";

// Model tier env vars — all remapped to agent's configured model so CLI
// internal tasks (WebFetch summarization, subagents) route through LiteLLM.
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



interface AgentConfig {
  instruction?: string;
  tools?: string[];
  policy?: Record<string, unknown>;
  mcp_servers?: Record<string, unknown>;
  user_token?: string;
  user_external_id?: string;
  credentials?: Record<string, string>;
  accessible_agents?: AccessibleAgent[];
  is_sub_agent?: boolean;
}

interface ModelConfig {
  model?: string;
  backend?: string;
  max_output_tokens?: number;
}

const MCP_GATEWAY_URL = process.env.MCP_GATEWAY_URL;

function buildMcpServers(agentConfig: AgentConfig): Record<string, any> | undefined {
  const servers: Record<string, any> = {};

  // Legacy stdio servers from ConfigMap / API
  if (agentConfig.mcp_servers) {
    Object.assign(servers, agentConfig.mcp_servers);
  }

  // MCP Gateway — single HTTP endpoint for all platform-managed tools.
  // URL comes from K8s env var; auth token comes from API per-request.
  if (MCP_GATEWAY_URL && agentConfig.user_token) {
    const agentId = process.env.AGENT_ID || "";
    servers["gateway"] = {
      type: "http",
      url: `${MCP_GATEWAY_URL}/mcp/v1/${agentId}`,
      headers: {
        Authorization: `Bearer ${agentConfig.user_token}`,
      },
    };
  }

  return Object.keys(servers).length > 0 ? servers : undefined;
}

function hasSessionHistory(claudeDir: string, sessionId: string): boolean {
  const projectsDir = path.join(claudeDir, "projects");
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
  type: "chunk" | "tool_use" | "tool_result" | "tool_progress" | "result" | "thinking" | "query_started" | "error";
  content?: string;
  name?: string;
  input?: unknown;
  tool_use_id?: string;
  is_error?: boolean;
  parent_tool_use_id?: string | null;
  // tool_progress fields
  tool_name?: string;
  elapsed_time_seconds?: number;
  // Error message (only on type: "error")
  message?: string;
  // Result metadata (only on type: "result")
  session_id?: string;
  duration_ms?: number;
  num_turns?: number;
  total_cost_usd?: number;
  usage?: Record<string, unknown>;
  structured_output?: unknown;
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
interface Attachment {
  type: string;
  media_type: string;
  data: string; // base64
}

/** A self-contained content segment with optional text and attachments.
 *  Used by workflow orchestration to combine multiple agent outputs. */
interface ContentPart {
  text?: string;
  attachments?: Attachment[];
}

function attachmentsToBlocks(atts: Attachment[]): Array<Record<string, unknown>> {
  return atts
    .filter((a) => a.type === "image")
    .map((a) => ({
      type: "image",
      source: { type: "base64", media_type: a.media_type, data: a.data },
    }));
}

/** Assemble SDK-compatible content from content_parts. */
function buildMessageContent(
  parts: ContentPart[],
): string | Array<Record<string, unknown>> {
  const hasAttachments = parts.some((p) => p.attachments?.length);
  // Single text-only part — pass as plain string (most common case)
  if (!hasAttachments && parts.length === 1 && parts[0].text) {
    return parts[0].text;
  }
  const blocks: Array<Record<string, unknown>> = [];
  for (const part of parts) {
    if (part.attachments?.length) {
      blocks.push(...attachmentsToBlocks(part.attachments));
    }
    if (part.text) {
      blocks.push({ type: "text", text: part.text });
    }
  }
  return blocks;
}

export async function* processMessage(
  sessionId: string,
  agentId: string,
  contentParts: ContentPart[],
  modelConfig: ModelConfig | null | undefined,
  agentConfig: AgentConfig,
  abortController?: AbortController,
  outputFormat?: { type: "json_schema"; schema: Record<string, unknown> },
): AsyncGenerator<SSEChunk> {
  const home = sessionHome(sessionId);
  const claudeDir = sessionClaudeDir(sessionId);
  const tmpDir = sessionTmp(sessionId);
  const venvDir = sessionVenvDir(sessionId);
  fs.mkdirSync(home, { recursive: true });
  fs.mkdirSync(claudeDir, { recursive: true });
  fs.mkdirSync(tmpDir, { recursive: true });
  fs.mkdirSync(path.dirname(venvDir), { recursive: true });

  const mc: ModelConfig = modelConfig ?? {};
  if (!mc.model || !mc.backend) {
    throw new Error("model_config.model and model_config.backend are required");
  }
  // Backend is the LiteLLM model-name prefix. If the stored model
  // already includes a prefix we use it verbatim, otherwise we join
  // backend + model. No allow-list — LiteLLM owns that validation.
  const resolvedModel = mc.model.includes("/") ? mc.model : `${mc.backend}/${mc.model}`;
  const canResume = hasSessionHistory(claudeDir, sessionId);

  const env: Record<string, string> = {
    ANTHROPIC_BASE_URL: LITELLM_URL,
    ANTHROPIC_API_KEY: LITELLM_API_KEY,
    // Propagate user JWT so LiteLLM hook can inject per-user Anthropic API key
    ...(agentConfig.user_token
      ? { ANTHROPIC_CUSTOM_HEADERS: `X-Aviary-User-Token: ${agentConfig.user_token}` }
      : {}),
    SESSION_WORKSPACE: home,
    SESSION_CLAUDE_DIR: claudeDir,
    SESSION_VENV_DIR: venvDir,
    SESSION_TMP: tmpDir,
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
    CLAUDE_CODE_MAX_RETRIES: "2",
    ...(mc.max_output_tokens != null
      ? { CLAUDE_CODE_MAX_OUTPUT_TOKENS: String(mc.max_output_tokens) }
      : {}),
    ...Object.fromEntries(MODEL_TIER_KEYS.map((k) => [k, resolvedModel])),
    ...Object.fromEntries(
      PASSTHROUGH_KEYS.filter((k) => process.env[k]).map((k) => [k, process.env[k]!]),
    ),
    // GitHub token — enables git/gh CLI authentication inside the sandbox.
    // GH_TOKEN is used by gh CLI, GITHUB_TOKEN by git credential helper.
    ...(agentConfig.credentials?.github_token
      ? {
          GITHUB_TOKEN: agentConfig.credentials.github_token,
          GH_TOKEN: agentConfig.credentials.github_token,
          // Configure git to use our credential helper for github.com
          GIT_CONFIG_COUNT: "1",
          GIT_CONFIG_KEY_0: "credential.https://github.com.helper",
          GIT_CONFIG_VALUE_0: "/app/scripts/git-credential-github.sh",
        }
      : {}),
  };

  // Build MCP servers (gateway + legacy)
  const mcpServers: Record<string, any> = buildMcpServers(agentConfig) ?? {};

  // A2A tools: start a local HTTP MCP server if accessible_agents is present and NOT a sub-agent.
  // Uses HTTP type (not SDK in-process type) so the CLI can reconnect on session resume.
  const accessibleAgents = agentConfig.accessible_agents ?? [];
  const isSubAgent = agentConfig.is_sub_agent === true;
  let a2aServer: A2AServer | null = null;
  const a2aToolNames: string[] = [];

  if (accessibleAgents.length > 0 && !isSubAgent && agentConfig.user_external_id) {
    a2aServer = await startA2AServer(accessibleAgents, {
      sessionId,
      userExternalId: agentConfig.user_external_id,
    });
    mcpServers["a2a"] = { type: "http", url: a2aServer.url };
    a2aToolNames.push(...a2aServer.toolNames);
  }

  // Build system prompt — use preset with append so SDK built-in tools
  // (like Agent) also receive the instruction.
  let appendPrompt = agentConfig.instruction || "";

  // Append sub-agent catalog (for main agents with A2A tools)
  if (a2aToolNames.length > 0) {
    const agentList = accessibleAgents
      .map((a) => `- @${a.slug}: ${a.description || a.name}`)
      .join("\n");
    appendPrompt += `\n\n## Available Sub-Agents\nYou can delegate tasks to these agents using the corresponding mcp__a2a__ask_{slug} tool:\n${agentList}`;
  }

  const systemPrompt = {
    type: "preset" as const,
    preset: "claude_code" as const,
    append: appendPrompt,
  };

  // Merge allowed tools with A2A tool names
  const allowedTools = [
    ...(agentConfig.tools ?? []),
    ...a2aToolNames,
  ];

  const options: Record<string, unknown> = {
    model: resolvedModel,
    systemPrompt,
    settingSources: ["user"],
    cwd: WORKSPACE_ROOT,
    pathToClaudeCodeExecutable: CLAUDE_CLI_PATH,
    permissionMode: "bypassPermissions" as const,
    allowedTools: allowedTools.length > 0 ? allowedTools : undefined,
    disallowedTools: ["WebSearch"],
    mcpServers: Object.keys(mcpServers).length > 0 ? mcpServers : undefined,
    env,
    includePartialMessages: true,
    ...(canResume ? {} : { extraArgs: { "session-id": sessionId } }),
    ...(canResume ? { resume: sessionId } : {}),
    ...(abortController ? { abortController } : {}),
    ...(outputFormat ? { outputFormat } : {}),
  };

  // PreToolUse hook: when SDK is about to call an A2A tool, capture the real
  // tool_use_id and pass it to the A2A server. This is the SDK's official hook
  // mechanism — guaranteed to fire before tools/call, no timing assumptions.
  if (a2aServer) {
    options.hooks = {
      PreToolUse: [{
        matcher: "mcp__a2a__ask_*",
        hooks: [async (input: any, toolUseID: string | undefined) => {
          if (toolUseID && input.tool_name?.startsWith("mcp__a2a__ask_")) {
            a2aServer!.enqueueToolUseId(input.tool_name, toolUseID);
          }
          return { continue: true };
        }],
      }],
    };
  }

  // Use async generator for prompt — required by SDK when using custom MCP tools
  async function* promptGenerator() {
    const messageContent = buildMessageContent(contentParts);

    yield {
      type: "user" as const,
      message: { role: "user" as const, content: messageContent },
      parent_tool_use_id: null,
      session_id: sessionId,
    };
  }

  let fullResponse = "";
  // Track cumulative lengths to extract deltas from partial snapshots.
  let emittedTextLen = 0;
  let emittedThinkingLen = 0;
  // Track tool_use IDs already emitted to avoid duplicates from partial messages
  const emittedToolIds = new Set<string>();
  // Whether we've received any stream_event deltas. When true (Anthropic),
  // text/thinking are handled via stream_event and assistant snapshots are
  // only used for tool_use. When false (ollama/vllm), assistant snapshots
  // are the sole source for all content types.
  let hasStreamDeltas = false;

  try {
    const stream = query({ prompt: promptGenerator(), options });
    yield { type: "query_started" } as SSEChunk;

    for await (const message of stream) {
      const msg = message as SDKMessage & Record<string, any>;

      if (msg.type === "stream_event") {
        // Real-time token-level streaming — emitted by Anthropic backends.
        // Non-Anthropic backends (ollama, vllm) don't emit these; they
        // fall through to the assistant snapshot handler below.
        const event = msg.event as Record<string, any>;
        if (event.type === "content_block_delta" && event.delta) {
          if (event.delta.type === "text_delta" && event.delta.text) {
            hasStreamDeltas = true;
            const delta = event.delta.text as string;
            emittedTextLen += delta.length;
            fullResponse += delta;
            yield { type: "chunk", content: delta };
          } else if (event.delta.type === "thinking_delta" && event.delta.thinking) {
            hasStreamDeltas = true;
            const delta = event.delta.thinking as string;
            emittedThinkingLen += delta.length;
            yield { type: "thinking", content: delta };
          }
        }
      } else if (msg.type === "assistant" && msg.message?.content) {
        const parentId = msg.parent_tool_use_id ?? null;
        for (const block of msg.message.content) {
          if (block.type === "thinking" && !hasStreamDeltas) {
            // Fallback path (ollama/vllm): no stream_event deltas available.
            // Block flushing creates multiple short blocks, each with its own
            // cumulative content. Detect new block when content is shorter.
            const thinking = (block.thinking ?? "") as string;
            if (thinking.length < emittedThinkingLen) {
              emittedThinkingLen = 0;
            }
            if (thinking.length > emittedThinkingLen) {
              const delta = thinking.slice(emittedThinkingLen);
              emittedThinkingLen = thinking.length;
              yield { type: "thinking", content: delta };
            }
          } else if (block.type === "text" && !hasStreamDeltas) {
            const text = block.text as string;
            if (text.length < emittedTextLen) {
              emittedTextLen = 0;
            }
            if (text.length > emittedTextLen) {
              const delta = text.slice(emittedTextLen);
              emittedTextLen = text.length;
              fullResponse += delta;
              yield { type: "chunk", content: delta };
            }
          } else if (block.type === "tool_use") {
            if (!emittedToolIds.has(block.id)) {
              emittedToolIds.add(block.id);
              yield {
                type: "tool_use",
                name: block.name,
                input: block.input,
                tool_use_id: block.id,
                ...(parentId ? { parent_tool_use_id: parentId } : {}),
              };
            }
          }
        }
      } else if (msg.type === "user" && msg.message?.content) {
        // SDKUserMessage — tool results sent back to the model after execution.
        // New assistant turn starts after this, so reset tracking.
        emittedTextLen = 0;
        emittedThinkingLen = 0;
        const parentId = msg.parent_tool_use_id ?? null;
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
                ...(block.is_error ? { is_error: true } : {}),
                ...(parentId ? { parent_tool_use_id: parentId } : {}),
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
          ...(msg.structured_output !== undefined ? { structured_output: msg.structured_output } : {}),
        };
      }
    }
  } catch (e) {
    if (abortController?.signal.aborted) {
      yield { type: "chunk", content: "[Cancelled by user]" };
      return;
    }
    console.error(`[agent ${agentId}/${sessionId}] SDK query error:`, e);
    const message = e instanceof Error ? e.message : String(e);
    yield { type: "error", message };
  } finally {
    // Shut down the A2A HTTP server after the message is fully processed
    a2aServer?.close();
  }
}

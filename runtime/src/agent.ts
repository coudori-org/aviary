/**
 * Agent runner using the official @anthropic-ai/claude-agent-sdk (TypeScript).
 *
 * The runtime is agent-agnostic: agent_id and session_id arrive in the request
 * body and are used to scope on-disk paths via the single-PVC layout in
 * constants.ts. All inference is routed through LiteLLM, and bubblewrap maps
 * the per-(agent, session) directories onto /workspace inside the sandbox —
 * see scripts/claude-sandbox.sh.
 */

import * as fs from "node:fs";
import * as fsp from "node:fs/promises";
import * as path from "node:path";

import { query, createSdkMcpServer, tool, type SDKMessage } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import { startA2AServer, type AccessibleAgent, type A2AServer } from "./a2a-tools.js";
import {
  SANDBOX_WORKSPACE,
  sessionClaudeDir,
  sessionSharedDir,
  sessionTmp,
  sessionVenvDir,
  workflowArtifactsDir,
  workflowArtifactPath,
} from "./constants.js";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Required environment variable ${name} is not set`);
  }
  return value;
}

const LITELLM_URL = requireEnv("LITELLM_URL");
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
const PASSTHROUGH_KEYS = ["PATH"] as const;



interface ModelConfig {
  model?: string;
  backend?: string;
  max_output_tokens?: number;
}

interface WorkflowRunRef {
  root_run_id: string;
  node_id: string;
}

interface ArtifactSpec {
  name: string;
  description?: string;
}

interface InputArtifactRef {
  upstream_node_id: string;
  artifact_name: string;
}

interface AgentConfig {
  agent_id: string;
  slug?: string;
  name?: string;
  description?: string | null;
  runtime_endpoint?: string | null;
  model_config?: ModelConfig | null;
  instruction?: string;
  tools?: string[];
  mcp_servers?: Record<string, unknown>;
  user_token?: string;
  user_external_id?: string;
  credentials?: Record<string, string>;
  accessible_agents?: AccessibleAgent[];
  is_sub_agent?: boolean;
  workflow_run?: WorkflowRunRef;
  artifacts?: ArtifactSpec[];
  input_artifacts?: InputArtifactRef[];
  /** Hard cap on assistant turns — safety net against verify-loop behaviour
   *  from weak local models. Undefined = SDK default (no cap). */
  max_turns?: number;
}

// Claude Code prefixes MCP tools as `mcp__{mcpServerKey}__{toolName}`;
// strip both that and our runtime-side key so we can hand LiteLLM the
// native `{server}__{tool}` tool names it aggregates under.
const MCP_RUNTIME_KEY = "gateway";
const CLAUDE_MCP_PREFIX = `mcp__${MCP_RUNTIME_KEY}__`;

function extractLitellmAllowedTools(tools: string[] | undefined): string[] {
  if (!tools) return [];
  const out: string[] = [];
  for (const t of tools) {
    if (t.startsWith(CLAUDE_MCP_PREFIX)) {
      out.push(t.slice(CLAUDE_MCP_PREFIX.length));
    }
  }
  return out;
}

function buildMcpServers(
  agentConfig: AgentConfig,
): Record<string, any> | undefined {
  const servers: Record<string, any> = {};

  // Legacy stdio servers from ConfigMap / API
  if (agentConfig.mcp_servers) {
    Object.assign(servers, agentConfig.mcp_servers);
  }

  // LiteLLM's aggregated MCP endpoint. Per-agent tool scoping is enforced
  // server-side: the runtime forwards the bound `{server}__{tool}` names in
  // `X-Aviary-Allowed-Tools`, and the `aviary_mcp_credentials` guardrail on
  // LiteLLM filters `tools/list` and rejects `tools/call` for anything not
  // in that list. The guardrail also validates the user JWT and injects
  // per-user Vault secrets into the outbound tool call arguments.
  if (agentConfig.user_token) {
    const allowed = extractLitellmAllowedTools(agentConfig.tools);
    servers[MCP_RUNTIME_KEY] = {
      type: "http",
      url: `${LITELLM_URL}/mcp`,
      headers: {
        Authorization: `Bearer ${agentConfig.user_token}`,
        "X-Aviary-Allowed-Tools": allowed.join(","),
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

export interface StructuredOutputField {
  name: string;
  type: "str" | "list";
  description?: string;
}

export interface StructuredOutputConfig {
  name: string;
  description?: string;
  fields: StructuredOutputField[];
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
}

// Dynamically-registered tools ride under this single SDK MCP server so the
// CLI-visible name is deterministic: `mcp__aviary_output__{entry.name}`.
// Callers choose when to fire each tool via their own system prompt.
const STRUCTURED_OUTPUT_MCP_SERVER = "aviary_output";
export const structuredOutputCliName = (toolName: string): string =>
  `mcp__${STRUCTURED_OUTPUT_MCP_SERVER}__${toolName}`;

function buildStructuredFieldSchema(field: StructuredOutputField): z.ZodType {
  const base: z.ZodType =
    field.type === "list" ? z.array(z.string()) : z.string();
  return field.description ? base.describe(field.description) : base;
}

function buildStructuredOutputsServer(configs: StructuredOutputConfig[]) {
  const tools = configs.map((cfg) => {
    const shape: Record<string, z.ZodType> = {};
    for (const field of cfg.fields) {
      shape[field.name] = buildStructuredFieldSchema(field);
    }
    const description =
      cfg.description ??
      `Call this tool to emit a structured \`${cfg.name}\` payload.`;
    return tool(cfg.name, description, shape, async () => ({
      content: [{ type: "text", text: `${cfg.name} recorded.` }],
    }));
  });
  return createSdkMcpServer({
    name: STRUCTURED_OUTPUT_MCP_SERVER,
    tools,
  });
}

const ARTIFACTS_MCP_SERVER = "aviary_artifacts";

function resolveSandboxWorkspacePath(sharedDir: string, sourcePath: string): string {
  let rel: string;
  if (sourcePath === "/workspace") {
    rel = "";
  } else if (sourcePath.startsWith("/workspace/")) {
    rel = sourcePath.slice("/workspace/".length);
  } else if (path.isAbsolute(sourcePath)) {
    throw new Error("source_path must be inside /workspace");
  } else {
    rel = sourcePath;
  }
  const resolvedShared = path.resolve(sharedDir);
  const resolved = path.resolve(resolvedShared, rel);
  if (resolved !== resolvedShared && !resolved.startsWith(resolvedShared + path.sep)) {
    throw new Error("source_path escapes /workspace");
  }
  return resolved;
}

function buildArtifactsServer(
  artifacts: ArtifactSpec[],
  sharedDir: string,
  rootRunId: string,
  nodeId: string,
) {
  const nameSchema =
    artifacts.length > 0
      ? z.enum(artifacts.map((a) => a.name) as [string, ...string[]])
      : z.string();
  const lines = artifacts
    .map((a) => `  - \`${a.name}\`${a.description ? ` — ${a.description}` : ""}`)
    .join("\n");
  const description =
    "Save a file or directory from /workspace as a named workflow artifact. " +
    "Downstream steps that depend on this node will see the saved content at " +
    "`/workspace/{artifact_name}` in their own sandbox. Call once per artifact.\n\n" +
    `Declared artifacts:\n${lines}`;

  const saveTool = tool(
    "save_as_artifact",
    description,
    {
      artifact_name: nameSchema.describe(
        "Which declared artifact this file belongs to. Must be one of the names above.",
      ),
      source_path: z
        .string()
        .describe(
          "Path inside the sandbox (relative to /workspace, or absolute starting with /workspace/). " +
            "May be a file or directory.",
        ),
    },
    async (args: { artifact_name: string; source_path: string }) => {
      let src: string;
      try {
        src = resolveSandboxWorkspacePath(sharedDir, args.source_path);
      } catch (e) {
        return {
          content: [{ type: "text", text: `save_as_artifact: ${(e as Error).message}` }],
          isError: true,
        };
      }
      if (!fs.existsSync(src)) {
        return {
          content: [{ type: "text", text: `save_as_artifact: ${args.source_path} does not exist` }],
          isError: true,
        };
      }
      const dst = workflowArtifactPath(rootRunId, nodeId, args.artifact_name);
      try {
        await fsp.rm(dst, { recursive: true, force: true });
        await fsp.mkdir(path.dirname(dst), { recursive: true });
        const stat = await fsp.stat(src);
        if (stat.isDirectory()) {
          await fsp.cp(src, dst, { recursive: true });
        } else {
          await fsp.copyFile(src, dst);
        }
      } catch (e) {
        return {
          content: [
            {
              type: "text",
              text: `save_as_artifact: copy failed — ${(e as Error).message}`,
            },
          ],
          isError: true,
        };
      }
      return {
        content: [
          { type: "text", text: `Saved artifact \`${args.artifact_name}\`.` },
        ],
      };
    },
  );

  return createSdkMcpServer({ name: ARTIFACTS_MCP_SERVER, tools: [saveTool] });
}

async function copyInputArtifacts(
  inputs: InputArtifactRef[],
  rootRunId: string,
  sharedDir: string,
): Promise<void> {
  const runRoot = workflowArtifactsDir(rootRunId);
  for (const ref of inputs) {
    const src = path.join(runRoot, ref.upstream_node_id, ref.artifact_name);
    if (!fs.existsSync(src)) {
      // Skip silently — upstream might not have produced this artifact.
      // The agent will find nothing at /workspace/{name} and can react.
      continue;
    }
    const dst = path.join(sharedDir, ref.artifact_name);
    await fsp.rm(dst, { recursive: true, force: true });
    const stat = await fsp.stat(src);
    if (stat.isDirectory()) {
      await fsp.cp(src, dst, { recursive: true });
    } else {
      await fsp.copyFile(src, dst);
    }
  }
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
  contentParts: ContentPart[],
  agentConfig: AgentConfig,
  abortController?: AbortController,
  outputFormat?: { type: "json_schema"; schema: Record<string, unknown> },
  structuredOutputs?: StructuredOutputConfig[],
): AsyncGenerator<SSEChunk> {
  const agentId = agentConfig.agent_id;
  const shared = sessionSharedDir(sessionId);
  const claudeDir = sessionClaudeDir(sessionId, agentId);
  const tmpDir = sessionTmp(sessionId, agentId);
  const venvDir = sessionVenvDir(sessionId, agentId);
  fs.mkdirSync(shared, { recursive: true });
  fs.mkdirSync(claudeDir, { recursive: true });
  fs.mkdirSync(tmpDir, { recursive: true });
  fs.mkdirSync(path.dirname(venvDir), { recursive: true });

  const mc: ModelConfig = agentConfig.model_config ?? {};
  if (!mc.model || !mc.backend) {
    throw new Error("agent_config.model_config.model and .backend are required");
  }
  // Backend is the LiteLLM model-name prefix. If the stored model
  // already includes a prefix we use it verbatim, otherwise we join
  // backend + model. No allow-list — LiteLLM owns that validation.
  const resolvedModel = mc.model.includes("/") ? mc.model : `${mc.backend}/${mc.model}`;
  const canResume = hasSessionHistory(claudeDir, sessionId);

  // Workflow-only setup: pre-copy upstream artifacts into the session's
  // shared dir and point the sandbox at the run's artifact tree. The
  // copy runs BEFORE the SDK spawns so agent code sees every requested
  // upstream as `/workspace/{name}` from turn zero.
  const workflowRun = agentConfig.workflow_run;
  const declaredArtifacts = Array.isArray(agentConfig.artifacts)
    ? agentConfig.artifacts.filter((a): a is ArtifactSpec => !!a?.name)
    : [];
  const inputArtifacts = Array.isArray(agentConfig.input_artifacts)
    ? agentConfig.input_artifacts.filter(
        (a): a is InputArtifactRef => !!a?.upstream_node_id && !!a?.artifact_name,
      )
    : [];
  let artifactsDir: string | null = null;
  if (workflowRun?.root_run_id) {
    artifactsDir = workflowArtifactsDir(workflowRun.root_run_id);
    fs.mkdirSync(artifactsDir, { recursive: true });
    if (inputArtifacts.length > 0) {
      await copyInputArtifacts(inputArtifacts, workflowRun.root_run_id, shared);
    }
  }

  const env: Record<string, string> = {
    ANTHROPIC_BASE_URL: LITELLM_URL,
    ANTHROPIC_API_KEY: LITELLM_API_KEY,
    // Propagate user JWT so LiteLLM hook can inject per-user Anthropic API key
    ...(agentConfig.user_token
      ? { ANTHROPIC_CUSTOM_HEADERS: `X-Aviary-User-Token: ${agentConfig.user_token}` }
      : {}),
    SESSION_WORKSPACE: shared,
    SESSION_CLAUDE_DIR: claudeDir,
    SESSION_VENV_DIR: venvDir,
    SESSION_TMP: tmpDir,
    ...(artifactsDir ? { SESSION_ARTIFACTS_DIR: artifactsDir } : {}),
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

  if (accessibleAgents.length > 0 && !isSubAgent) {
    a2aServer = await startA2AServer(accessibleAgents, {
      sessionId,
      userToken: agentConfig.user_token,
    });
    mcpServers["a2a"] = { type: "http", url: a2aServer.url };
    a2aToolNames.push(...a2aServer.toolNames);
  }

  let systemPrompt = agentConfig.instruction || "";

  if (a2aToolNames.length > 0) {
    const agentList = accessibleAgents
      .map((a) => `- @${a.slug}: ${a.description || a.name}`)
      .join("\n");
    systemPrompt += `\n\n## Available Sub-Agents\nYou can delegate tasks to these agents using the corresponding mcp__a2a__ask_{slug} tool:\n${agentList}`;
  }

  // Dynamic structured-output tools — one MCP tool per entry, bound under
  // the `aviary_output` SDK MCP server. Callers (workflow assistant,
  // agent auto-complete, etc.) describe each tool's trigger / contents in
  // their own system prompt; the runtime just exposes the tools and lets
  // tool_use events flow through the normal stream.
  const structuredToolNames: string[] = [];
  const validStructuredOutputs = (structuredOutputs ?? []).filter(
    (c) => c?.name && Array.isArray(c.fields),
  );
  if (validStructuredOutputs.length > 0) {
    mcpServers[STRUCTURED_OUTPUT_MCP_SERVER] = buildStructuredOutputsServer(
      validStructuredOutputs,
    );
    for (const cfg of validStructuredOutputs) {
      structuredToolNames.push(structuredOutputCliName(cfg.name));
    }
  }

  // Workflow artifacts tool — only when the step declared artifacts AND we
  // have a workflow_run to attribute them to. Runs entirely in-process so
  // it can touch the PVC directly (the sandbox's /artifacts mount is ro).
  const artifactToolNames: string[] = [];
  if (declaredArtifacts.length > 0 && workflowRun?.root_run_id) {
    mcpServers[ARTIFACTS_MCP_SERVER] = buildArtifactsServer(
      declaredArtifacts,
      shared,
      workflowRun.root_run_id,
      workflowRun.node_id,
    );
    artifactToolNames.push(`mcp__${ARTIFACTS_MCP_SERVER}__save_as_artifact`);
  }

  // Merge allowed tools with A2A tool names and any dynamic tools.
  const allowedTools = [
    ...(agentConfig.tools ?? []),
    ...a2aToolNames,
    ...structuredToolNames,
    ...artifactToolNames,
  ];

  const options: Record<string, unknown> = {
    model: resolvedModel,
    systemPrompt,
    settingSources: ["user"],
    cwd: SANDBOX_WORKSPACE,
    pathToClaudeCodeExecutable: CLAUDE_CLI_PATH,
    permissionMode: "bypassPermissions" as const,
    allowedTools: allowedTools.length > 0 ? allowedTools : undefined,
    disallowedTools: ["WebSearch"],
    mcpServers: Object.keys(mcpServers).length > 0 ? mcpServers : undefined,
    env,
    stderr: (data: string) => {
      // Surface Claude CLI stderr to pod logs so exit-1 root causes are
      // visible without needing DEBUG_CLAUDE_AGENT_SDK + tailing files.
      const text = data.trim();
      if (text) console.error(`[cli-stderr ${agentId}/${sessionId}] ${text}`);
    },
    includePartialMessages: true,
    ...(canResume ? {} : { extraArgs: { "session-id": sessionId } }),
    ...(canResume ? { resume: sessionId } : {}),
    ...(abortController ? { abortController } : {}),
    ...(outputFormat ? { outputFormat } : {}),
    ...(typeof agentConfig.max_turns === "number" && agentConfig.max_turns > 0
      ? { maxTurns: agentConfig.max_turns }
      : {}),
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
        // Emit result metadata (cost, usage, duration). SDK-native
        // `msg.structured_output` only surfaces when the built-in
        // outputFormat option was used — unused in our caller paths now,
        // but kept so the shape is forward-compatible.
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
    console.error(`[agent ${agentId}/${sessionId}] SDK query error:`, e);
    const message = e instanceof Error ? e.message : String(e);
    yield { type: "error", message };
  } finally {
    // Shut down the A2A HTTP server after the message is fully processed
    a2aServer?.close();
  }
}

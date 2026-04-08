/**
 * Agent-to-Agent (A2A) calling tools.
 *
 * Runs a lightweight HTTP MCP server (JSON-RPC over HTTP POST) that exposes
 * one tool per accessible agent. Each tool calls the API server's A2A endpoint
 * which handles auth, ACL, agent provisioning, and dual-streams the response
 * (SSE to caller + Redis pub/sub to frontend).
 */

import * as http from "node:http";
import * as crypto from "node:crypto";

const API_URL = process.env.AVIARY_API_URL || "";
const A2A_TIMEOUT = parseInt(process.env.A2A_CALL_TIMEOUT_SECONDS ?? "120", 10) * 1000;

const SUB_AGENT_PREFIX = `[SUB-AGENT MODE]
You are being invoked as a sub-agent by another agent to perform a specific task.
Guidelines:
- Focus exclusively on the task described in the message below.
- For large outputs (data, code, detailed results), write files to /home/shared/ and return a concise summary with file paths.
- The calling agent can read files from /home/shared/ to access your detailed results.
- Keep your response focused and actionable.

---

`;

export interface AccessibleAgent {
  slug: string;
  name: string;
  description: string | null;
}

export interface A2AContext {
  sessionId: string;
  userToken: string;
  credentials?: Record<string, string>;
}

/**
 * Call the sub-agent via the API server's A2A endpoint.
 * The API handles auth, ACL, provisioning, and dual-streams to frontend via Redis.
 */
async function callSubAgent(
  agent: AccessibleAgent,
  message: string,
  ctx: A2AContext,
  parentToolUseId: string,
): Promise<string> {
  if (!API_URL) {
    return "Error: AVIARY_API_URL not configured — cannot call sub-agents.";
  }

  const url = `${API_URL}/a2a/${agent.slug}/message`;

  const body = {
    content: message,
    session_id: ctx.sessionId,
    parent_tool_use_id: parentToolUseId,
  };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), A2A_TIMEOUT);

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${ctx.userToken}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!resp.ok) {
      const errText = await resp.text();
      return `Error calling agent @${agent.slug}: HTTP ${resp.status} — ${errText}`;
    }

    // Parse SSE stream and collect text chunks
    let result = "";
    const reader = resp.body?.getReader();
    if (!reader) return "Error: No response stream";

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const chunk = JSON.parse(line.slice(6));
          if (chunk.type === "chunk" && chunk.content) {
            result += chunk.content;
          }
        } catch {
          // skip malformed JSON
        }
      }
    }

    return result || "(No response from sub-agent)";
  } catch (e: any) {
    if (e.name === "AbortError") {
      return `Error: Sub-agent @${agent.slug} timed out after ${A2A_TIMEOUT / 1000}s`;
    }
    return `Error calling agent @${agent.slug}: ${e.message}`;
  } finally {
    clearTimeout(timeout);
  }
}

// ── Lightweight MCP HTTP Server (JSON-RPC) ──────────────────

interface McpTool {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (args: Record<string, unknown>) => Promise<{ content: Array<{ type: string; text: string }> }>;
}

function buildToolDefinitions(
  agents: AccessibleAgent[],
  ctx: A2AContext,
  toolUseIdQueues: Map<string, string[]>,
): McpTool[] {
  return agents.map((agent) => {
    const toolName = `ask_${agent.slug}`;
    // Pre-create queue for this tool
    toolUseIdQueues.set(toolName, []);
    return {
      name: toolName,
      description: agent.description || `Call agent: ${agent.name}`,
      inputSchema: {
        type: "object",
        properties: {
          message: { type: "string", description: "The task or question to send to this agent" },
        },
        required: ["message"],
      },
      handler: async (args: Record<string, unknown>) => {
        const fullMessage = SUB_AGENT_PREFIX + String(args.message ?? "");
        // Dequeue the tool_use_id enqueued by PreToolUse hook.
        // PreToolUse fires before tools/call, guaranteed by SDK lifecycle.
        // Keyed by tool name so parallel calls to different agents are safe.
        // Same-agent parallel calls are ordered because PreToolUse fires sequentially.
        const queue = toolUseIdQueues.get(toolName);
        const parentToolUseId = queue?.shift() || `a2a_${crypto.randomUUID()}`;
        const result = await callSubAgent(agent, fullMessage, ctx, parentToolUseId);
        return { content: [{ type: "text", text: result }] };
      },
    };
  });
}

function handleJsonRpc(
  tools: McpTool[],
  body: { jsonrpc: string; id: unknown; method: string; params?: Record<string, unknown> },
): Promise<Record<string, unknown>> {
  const { id, method, params } = body;

  if (method === "initialize") {
    return Promise.resolve({
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "a2a", version: "1.0.0" },
      },
    });
  }

  if (method === "notifications/initialized") {
    return Promise.resolve({ jsonrpc: "2.0", id, result: {} });
  }

  if (method === "tools/list") {
    return Promise.resolve({
      jsonrpc: "2.0",
      id,
      result: {
        tools: tools.map((t) => ({
          name: t.name,
          description: t.description,
          inputSchema: t.inputSchema,
        })),
      },
    });
  }

  if (method === "tools/call") {
    const toolName = (params as any)?.name as string;
    const toolArgs = ((params as any)?.arguments ?? {}) as Record<string, unknown>;
    const tool = tools.find((t) => t.name === toolName);
    if (!tool) {
      return Promise.resolve({
        jsonrpc: "2.0",
        id,
        result: { content: [{ type: "text", text: `Unknown tool: ${toolName}` }], isError: true },
      });
    }
    return tool.handler(toolArgs).then((result) => ({
      jsonrpc: "2.0",
      id,
      result,
    }));
  }

  return Promise.resolve({
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `Method not found: ${method}` },
  });
}

export interface A2AServer {
  url: string;
  close: () => void;
  toolNames: string[];
  /** Enqueue a tool_use_id for the given MCP tool name (called from PreToolUse hook). */
  enqueueToolUseId: (mcpToolName: string, id: string) => void;
}

/**
 * Start a local HTTP MCP server and return its URL.
 * The server lives for the duration of one processMessage call.
 */
export async function startA2AServer(
  agents: AccessibleAgent[],
  ctx: A2AContext,
): Promise<A2AServer> {
  // Per-tool FIFO queues of tool_use_ids, populated by PreToolUse hook (agent.ts).
  // SDK guarantees PreToolUse fires before tools/call, so the queue always has
  // an entry when the handler runs. Keyed by tool name for parallel safety.
  const toolUseIdQueues = new Map<string, string[]>();

  const tools = buildToolDefinitions(agents, ctx, toolUseIdQueues);
  const toolNames = tools.map((t) => `mcp__a2a__${t.name}`);

  const server = http.createServer(async (req, res) => {
    if (req.method === "POST") {
      let body = "";
      for await (const chunk of req) body += chunk;

      try {
        const parsed = JSON.parse(body);
        const response = await handleJsonRpc(tools, parsed);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify(response));
      } catch {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } }));
      }
      return;
    }

    if (req.method === "DELETE") {
      res.writeHead(200);
      res.end();
      return;
    }

    res.writeHead(405);
    res.end();
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const addr = server.address() as { port: number };

  return {
    url: `http://127.0.0.1:${addr.port}/mcp`,
    close: () => server.close(),
    toolNames,
    enqueueToolUseId: (mcpToolName: string, id: string) => {
      // mcpToolName is the MCP-qualified name like "mcp__a2a__ask_slug",
      // strip prefix to get the local tool name "ask_slug"
      const localName = mcpToolName.replace("mcp__a2a__", "");
      const queue = toolUseIdQueues.get(localName);
      if (queue) queue.push(id);
    },
  };
}

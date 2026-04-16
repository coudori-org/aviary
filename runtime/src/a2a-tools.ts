/**
 * Agent-to-Agent (A2A) calling tools.
 *
 * Runs a lightweight HTTP MCP server (JSON-RPC over HTTP POST) that exposes
 * one tool per accessible agent. The API server pre-resolves accessible
 * agents (with ACL) at chat-start and hands the runtime a trusted list
 * containing each sub-agent's `agent_id` + `runtime_endpoint`. Each A2A
 * tool POSTs straight to the supervisor's `/v1/sessions/{sid}/a2a` endpoint,
 * which streams the sub-agent SSE back and tags tool events into the parent
 * session's Redis buffer. The runtime never re-validates auth/ACL.
 */

import * as http from "node:http";
import * as crypto from "node:crypto";

const SUPERVISOR_URL = process.env.AVIARY_SUPERVISOR_URL;
const A2A_TIMEOUT = parseInt(process.env.A2A_CALL_TIMEOUT_SECONDS ?? "1800", 10) * 1000;

const SUB_AGENT_PREFIX = `[SUB-AGENT MODE]
You are being invoked as a sub-agent by another agent to perform a specific task.
Guidelines:
- Focus exclusively on the task described in the message below.
- Your /workspace directory is shared with the calling agent. Write output files there if needed and return a summary with file paths.
- Keep your response focused and actionable.

---

`;

/**
 * Full sub-agent spec as it arrives in the parent's agent_config.
 * Mirrors the server-side `agent_config` contract: every field the
 * sub-agent runtime needs to execute is here, so the parent's A2A server
 * can forward it to the supervisor unchanged.
 */
export interface AccessibleAgent {
  agent_id: string;
  slug: string;
  name: string;
  description: string | null;
  runtime_endpoint: string | null;
  model_config: Record<string, unknown>;
  instruction: string;
  tools: string[];
  mcp_servers: Record<string, unknown>;
}

export interface A2AContext {
  sessionId: string;
  /** User JWT — forwarded to the supervisor as `Authorization: Bearer`.
   *  The supervisor validates it and injects identity + per-user Vault
   *  credentials into the sub-agent runtime body. */
  userToken: string | undefined;
}

async function callSubAgent(
  agent: AccessibleAgent,
  message: string,
  ctx: A2AContext,
  parentToolUseId: string,
): Promise<string> {
  const url = `${SUPERVISOR_URL}/v1/sessions/${ctx.sessionId}/a2a`;

  const body = {
    parent_session_id: ctx.sessionId,
    parent_tool_use_id: parentToolUseId,
    agent_config: {
      agent_id: agent.agent_id,
      slug: agent.slug,
      name: agent.name,
      description: agent.description,
      runtime_endpoint: agent.runtime_endpoint,
      model_config: agent.model_config,
      instruction: agent.instruction,
      tools: agent.tools,
      mcp_servers: agent.mcp_servers,
    },
    content_parts: [{ text: message }],
  };

  if (!ctx.userToken) {
    return `Error calling agent @${agent.slug}: missing user token (required for supervisor auth)`;
  }

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
      console.error(`A2A call failed: ${agent.slug} HTTP ${resp.status}`, errText);
      return `Error calling agent @${agent.slug}: HTTP ${resp.status} — ${errText}`;
    }

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
    return Promise.resolve({ __stream_tool_call: true, id, params } as any);
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

export async function startA2AServer(
  agents: AccessibleAgent[],
  ctx: A2AContext,
): Promise<A2AServer> {
  if (!SUPERVISOR_URL) {
    throw new Error(
      "AVIARY_SUPERVISOR_URL must be set when accessible_agents is provided",
    );
  }
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

        if (response && (response as any).__stream_tool_call) {
          const { id, params: rpcParams } = response as any;
          const toolName = rpcParams?.name as string;
          const toolArgs = (rpcParams?.arguments ?? {}) as Record<string, unknown>;
          const progressToken = rpcParams?._meta?.progressToken;
          const tool = tools.find((t) => t.name === toolName);

          res.writeHead(200, {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
          });

          if (!tool) {
            const errResult = { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: `Unknown tool: ${toolName}` }], isError: true } };
            res.write(`event: message\ndata: ${JSON.stringify(errResult)}\n\n`);
            res.end();
            return;
          }

          let progress = 0;
          const progressInterval = progressToken ? setInterval(() => {
            progress++;
            const notification = {
              jsonrpc: "2.0",
              method: "notifications/progress",
              params: { progressToken, progress, total: 0 },
            };
            res.write(`event: message\ndata: ${JSON.stringify(notification)}\n\n`);
          }, 30_000) : null;

          try {
            const result = await tool.handler(toolArgs);
            const finalResponse = { jsonrpc: "2.0", id, result };
            res.write(`event: message\ndata: ${JSON.stringify(finalResponse)}\n\n`);
          } catch (e: any) {
            const errResponse = { jsonrpc: "2.0", id, result: { content: [{ type: "text", text: `Error: ${e.message}` }], isError: true } };
            res.write(`event: message\ndata: ${JSON.stringify(errResponse)}\n\n`);
          } finally {
            if (progressInterval) clearInterval(progressInterval);
            res.end();
          }
          return;
        }

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
      const localName = mcpToolName.replace("mcp__a2a__", "");
      const queue = toolUseIdQueues.get(localName);
      if (queue) queue.push(id);
    },
  };
}

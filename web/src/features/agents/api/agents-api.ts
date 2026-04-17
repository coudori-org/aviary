import { http } from "@/lib/http";
import type { Agent, McpToolBinding, Session } from "@/types";

/**
 * Agents API — thin typed wrappers over the REST endpoints.
 *
 * Caller responsibility: catch errors at the consuming page/component
 * boundary. Mutations throw ApiError on failure.
 */

export interface AgentListResponse {
  items: Agent[];
  total: number;
}

export interface AgentMutationData {
  name: string;
  slug: string;
  description: string;
  instruction: string;
  model_config: {
    backend: string;
    model: string;
    max_output_tokens: number;
  };
  tools: string[];
}

export const agentsApi = {
  list(search?: string) {
    const path = search ? `/catalog/search?q=${encodeURIComponent(search)}` : "/agents";
    return http.get<AgentListResponse>(path);
  },

  get(id: string) {
    return http.get<Agent>(`/agents/${id}`);
  },

  create(data: AgentMutationData) {
    return http.post<Agent>("/agents", data);
  },

  update(id: string, data: AgentMutationData) {
    return http.put<Agent>(`/agents/${id}`, data);
  },

  remove(id: string) {
    return http.delete(`/agents/${id}`);
  },

  // MCP tool bindings
  getMcpTools(agentId: string) {
    return http.get<McpToolBinding[]>(`/mcp/agents/${agentId}/tools`);
  },

  setMcpTools(agentId: string, toolIds: string[]) {
    return http.put(`/mcp/agents/${agentId}/tools`, { tool_ids: toolIds });
  },

  // Sessions
  listSessions(agentId: string) {
    return http.get<{ items: Session[] }>(`/agents/${agentId}/sessions`);
  },

  createSession(agentId: string) {
    return http.post<Session>(`/agents/${agentId}/sessions`, { type: "private" });
  },
};

// --- Inference / models ---

export interface ModelOption {
  id: string;
  name: string;
  backend: string;
  model_info: {
    max_tokens?: number;
    _ui?: {
      default_model?: boolean;
      capabilities?: string[];
    };
  };
}

export const modelsApi = {
  list() {
    return http.get<{ models: ModelOption[] }>("/inference/models");
  },
};

// --- ACL ---

export interface ACLEntry {
  id: string;
  agent_id: string;
  user_id: string | null;
  team_id: string | null;
  role: string;
  created_at: string;
}

export const aclApi = {
  list(agentId: string) {
    return http.get<{ items: ACLEntry[] }>(`/agents/${agentId}/acl`);
  },
  add(agentId: string, body: { user_id: string; role: string }) {
    return http.post<ACLEntry>(`/agents/${agentId}/acl`, body);
  },
  remove(agentId: string, aclId: string) {
    return http.delete(`/agents/${agentId}/acl/${aclId}`);
  },
};

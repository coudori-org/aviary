export interface User {
  id: string;
  external_id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  created_at: string;
}

export interface AuthConfig {
  issuer: string;
  client_id: string;
  authorization_endpoint: string;
  token_endpoint: string;
  end_session_endpoint: string;
}

export interface Agent {
  id: string;
  name: string;
  slug: string;
  description?: string;
  owner_id: string;
  instruction: string;
  model_config: ModelConfig;
  tools: string[];
  mcp_servers: McpServer[];
  visibility: "public" | "team" | "private";
  category?: string;
  icon?: string;
  status: "active" | "disabled" | "deleted";
  created_at: string;
  updated_at: string;
}

export interface ModelConfig {
  backend: "claude" | "ollama" | "vllm";
  model: string;
  temperature?: number;
  maxTokens?: number;
}

export interface McpServer {
  name: string;
  command: string;
  args: string[];
}

export interface Session {
  id: string;
  agent_id: string;
  type: "private" | "team";
  created_by: string;
  team_id?: string;
  title?: string;
  status: "active" | "archived";
  pod_name?: string;
  last_message_at?: string;
  created_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  sender_type: "user" | "agent";
  sender_id?: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

// --- Streaming block types ---

export interface TextBlock {
  type: "text";
  id: string;
  content: string;
}

export interface ToolCallBlock {
  type: "tool_call";
  id: string;
  name: string;
  input: Record<string, unknown>;
  status: "running" | "complete";
  result?: string;
  is_error?: boolean;
  elapsed?: number;
  parent_tool_use_id?: string;
  children?: ToolCallBlock[];
}

export type StreamBlock = TextBlock | ToolCallBlock;

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

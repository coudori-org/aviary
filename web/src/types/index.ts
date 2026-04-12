export interface UserPreferences {
  /** Sidebar agent group order in By Agent view (UUID array). */
  sidebar_agent_order?: string[];
  /** Per-agent session order in By Agent view. Map of agent UUID → session UUID array. */
  sidebar_session_order?: Record<string, string[]>;
  /** Allow forward-compatibility for new keys without bumping the type. */
  [key: string]: unknown;
}

export interface User {
  id: string;
  external_id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  preferences?: UserPreferences;
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
  /** LiteLLM model-name prefix (``anthropic``, ``ollama``, ``vllm``, …).
   *  Opaque to the frontend — sourced from `/api/inference/models`. */
  backend: string;
  model: string;
  max_output_tokens?: number;
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
  children?: StreamBlock[];
}

export interface ThinkingBlock {
  type: "thinking";
  id: string;
  content: string;
}

export type StreamBlock = TextBlock | ToolCallBlock | ThinkingBlock;

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

// --- File attachment types ---

export interface FileRef {
  file_id: string;
  filename: string;
  content_type: string;
}

export interface PendingAttachment {
  localId: string;
  file: File;
  preview: string;
  status: "uploading" | "done" | "error";
  fileRef?: FileRef;
}

// --- Workflow types ---

export interface Workflow {
  id: string;
  name: string;
  slug: string;
  description?: string;
  owner_id: string;
  visibility: "public" | "team" | "private";
  definition: WorkflowDefinition;
  model_config: ModelConfig;
  status: "draft" | "active" | "deleted";
  created_at: string;
  updated_at: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: { x: number; y: number; zoom: number };
}

export interface WorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  data?: Record<string, unknown>;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  triggered_by: string;
  trigger_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at?: string;
  completed_at?: string;
  error?: string;
  created_at: string;
  node_runs: WorkflowNodeRun[];
}

export interface WorkflowNodeRun {
  id: string;
  node_id: string;
  node_type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

// --- MCP Gateway types ---

export interface McpServerInfo {
  id: string;
  name: string;
  description: string | null;
  tags: string[];
  tool_count: number;
}

export interface McpToolInfo {
  id: string;
  server_id: string;
  server_name: string;
  name: string;
  description: string | null;
  input_schema: Record<string, unknown>;
  qualified_name: string;
}

export interface McpToolBinding {
  id: string;
  agent_id: string;
  tool: McpToolInfo;
}

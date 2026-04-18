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
  icon?: string;
  status: "active" | "disabled" | "deleted";
  created_at: string;
  updated_at: string;
}

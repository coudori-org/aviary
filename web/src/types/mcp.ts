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

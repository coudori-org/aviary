/**
 * Internal form types for the agent create/edit flow.
 */

export interface AgentFormData {
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
  mcp_tool_ids: string[];
}

export const DEFAULT_AGENT_FORM_DATA: AgentFormData = {
  name: "",
  slug: "",
  description: "",
  instruction: "",
  model_config: {
    // Populated from the LiteLLM catalogue on first load; the form
    // picks the first available backend if this is still empty.
    backend: "",
    model: "",
    max_output_tokens: 8000,
  },
  tools: [],
  mcp_tool_ids: [],
};

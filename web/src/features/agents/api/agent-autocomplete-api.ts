import { http } from "@/lib/http";
import type { McpToolInfo } from "@/types";

export interface AutocompleteRequest {
  name: string;
  description: string;
  instruction: string;
  model_config: { backend: string; model: string; max_output_tokens: number };
  mcp_tool_ids: string[];
  user_prompt?: string;
}

export interface AutocompleteResponse {
  name: string;
  description: string;
  instruction: string;
  mcp_tool_ids: string[];
  tool_info: McpToolInfo[];
}

export const agentAutocompleteApi = {
  run(body: AutocompleteRequest) {
    return http.post<AutocompleteResponse>("/agents/autocomplete", body);
  },
};

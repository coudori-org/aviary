import { http } from "@/lib/http";
import type { McpServerInfo, McpToolInfo } from "@/types";

export const mcpApi = {
  listServers() {
    return http.get<McpServerInfo[]>("/mcp/servers");
  },

  listServerTools(serverId: string) {
    return http.get<McpToolInfo[]>(`/mcp/servers/${serverId}/tools`);
  },

  searchTools(query: string) {
    return http.get<McpToolInfo[]>(`/mcp/tools/search?q=${encodeURIComponent(query)}`);
  },
};

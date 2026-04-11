import { http } from "@/lib/http";

/**
 * Search API client — backend full-text search across messages.
 *
 * The backend is responsible for ACL filtering (only sessions the caller
 * can access). The frontend just passes the query and renders results.
 */

export interface MessageSearchHit {
  message_id: string;
  session_id: string;
  session_title: string | null;
  agent_id: string;
  agent_name: string;
  agent_icon: string | null;
  sender_type: "user" | "agent";
  snippet: string;
  created_at: string;
}

export interface MessageSearchResponse {
  items: MessageSearchHit[];
  total: number;
}

export const searchApi = {
  searchMessages(query: string): Promise<MessageSearchResponse> {
    return http.get<MessageSearchResponse>(
      `/search/messages?q=${encodeURIComponent(query)}`,
    );
  },
};

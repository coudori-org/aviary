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

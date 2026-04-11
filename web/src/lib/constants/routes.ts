/**
 * All client-side route paths centralized here.
 * No more hard-coded strings sprinkled across the codebase.
 */
export const routes = {
  home: "/",
  login: "/login",
  authCallback: "/auth/callback",
  agents: "/agents",
  agentNew: "/agents/new",
  agent: (id: string) => `/agents/${id}`,
  agentEdit: (id: string) => `/agents/${id}/edit`,
  agentSessions: (id: string) => `/agents/${id}/sessions`,
  agentSettings: (id: string) => `/agents/${id}/settings`,
  session: (id: string) => `/sessions/${id}`,
} as const;

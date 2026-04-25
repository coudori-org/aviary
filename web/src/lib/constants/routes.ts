export const routes = {
  home: "/",
  login: "/login",
  authCallback: "/auth/callback",
  agents: "/agents",
  agentNew: "/agents/new",
  agent: (id: string) => `/agents/${id}`,
  agentEdit: (id: string) => `/agents/${id}/edit`,
  agentSessions: (id: string) => `/agents/${id}/sessions`,
  agentDetail: (id: string) => `/agents/${id}/detail`,
  /** Chat home for an agent; optional session deep-link via ?session=. */
  agentChat: (agentId: string, sessionId?: string) =>
    sessionId ? `/agents/${agentId}?session=${sessionId}` : `/agents/${agentId}`,
  /** Legacy session route — kept for backward-compat redirect. */
  session: (id: string) => `/sessions/${id}`,
  workflows: "/workflows",
  workflowNew: "/workflows/new",
  workflow: (id: string) => `/workflows/${id}`,
  workflowDetail: (id: string) => `/workflows/${id}/detail`,
  workflowRuns: (id: string) => `/workflows/${id}/runs`,
  /** Builder deep-link: open workflow at a specific version (and run,
   *  if any). `versionId` may be the "draft" sentinel for draft runs. */
  workflowAtVersion: (id: string, versionId: string, runId?: string) =>
    runId
      ? `/workflows/${id}?runId=${runId}&versionId=${versionId}`
      : `/workflows/${id}?versionId=${versionId}`,
  marketplace: "/marketplace",
  marketplaceItem: (id: string) => `/marketplace/${id}`,
  settings: "/settings",
  settingsTab: (tab: "profile" | "credentials" | "preferences") =>
    `/settings?tab=${tab}`,
} as const;

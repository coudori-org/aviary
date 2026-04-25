/**
 * Credentials surface — *placeholder* until the backend exposes per-user
 * Vault management. The real path is `secret/aviary/credentials/{sub}/{key}`
 * (see CLAUDE.md). Today we only render whether a key is connected; the
 * UI mutates nothing.
 */

export interface CredentialKey {
  /** Stable key as stored in Vault (also the path leaf). */
  id: string;
  /** Human-readable label. */
  label: string;
  /** What this credential unlocks for the user. */
  description: string;
  /** Whether the key is presently set in Vault. */
  status: "connected" | "missing";
  /** When the value was last rotated, if known. */
  last_rotated?: string;
  /** Where the key gets injected at runtime — surfaced in the UI for
   *  context. */
  scope: string;
}

const NOW = Date.now();
const day = (n: number) => new Date(NOW - n * 86_400_000).toISOString();

const MOCK: CredentialKey[] = [
  {
    id: "anthropic-api-key",
    label: "Anthropic API key",
    description:
      "Used by LiteLLM when this user calls Claude through the gateway.",
    status: "connected",
    last_rotated: day(12),
    scope: "Inference",
  },
  {
    id: "github-token",
    label: "GitHub token",
    description:
      "Authenticates `git`, `gh`, and the GitHub MCP server inside the runtime.",
    status: "connected",
    last_rotated: day(34),
    scope: "Runtime · MCP",
  },
  {
    id: "slack-token",
    label: "Slack token",
    description: "Lets the Slack MCP server post on your behalf.",
    status: "missing",
    scope: "MCP",
  },
  {
    id: "jira-token",
    label: "Jira token",
    description: "Lets the Jira MCP server read tickets and transition status.",
    status: "missing",
    scope: "MCP",
  },
  {
    id: "notion-token",
    label: "Notion token",
    description: "Lets the Notion MCP server read and write pages.",
    status: "missing",
    scope: "MCP",
  },
];

export const credentialsApi = {
  async list(): Promise<CredentialKey[]> {
    return new Promise((resolve) => setTimeout(() => resolve(MOCK), 80));
  },
};

import { http } from "@/lib/http";
import type { Workflow, WorkflowRun } from "@/types";
import type { PlanOp } from "../lib/assistant-plan";

// --- Assistant streaming ---

export type AssistantStreamEvent =
  | { type: "chunk"; content: string; stream_id?: string }
  | { type: "thinking"; content: string; stream_id?: string }
  | { type: "tool_use"; name: string; input: Record<string, unknown>; tool_use_id: string; stream_id?: string; parent_tool_use_id?: string }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error?: boolean; stream_id?: string }
  | { type: "stream_started"; stream_id: string }
  | { type: "query_started"; stream_id?: string }
  | { type: "result"; stream_id?: string }
  | { type: "assistant_done"; reply: string; plan: PlanOp[] }
  | { type: "error"; message: string }
  | { type: "other" };

export interface AssistantStreamCallbacks {
  onEvent: (event: AssistantStreamEvent) => void;
  signal?: AbortSignal;
}

export interface WorkflowListResponse {
  items: Workflow[];
  total: number;
}

export interface WorkflowRunListResponse {
  items: WorkflowRun[];
  total: number;
}

export interface WorkflowCreateData {
  name: string;
  slug: string;
  description?: string;
  model_config: { backend: string; model: string };
}

export interface WorkflowUpdateData {
  name?: string;
  description?: string;
  definition?: Record<string, unknown>;
  model_config?: { backend: string; model: string };
}

export interface WorkflowVersionData {
  id: string;
  workflow_id: string;
  version: number;
  deployed_by: string;
  deployed_at: string;
  /** Frozen definition snapshot at deploy time. The builder uses this
   *  to render past versions read-only and to seed a new draft when
   *  the user rolls back via Edit. */
  definition: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
    viewport?: { x: number; y: number; zoom: number };
  };
}

export const workflowsApi = {
  list() {
    return http.get<WorkflowListResponse>("/workflows");
  },

  get(id: string) {
    return http.get<Workflow>(`/workflows/${id}`);
  },

  create(data: WorkflowCreateData) {
    return http.post<Workflow>("/workflows", data);
  },

  update(id: string, data: WorkflowUpdateData) {
    return http.put<Workflow>(`/workflows/${id}`, data);
  },

  remove(id: string) {
    return http.delete(`/workflows/${id}`);
  },

  deploy(id: string) {
    return http.post<WorkflowVersionData>(`/workflows/${id}/deploy`, {});
  },

  edit(id: string) {
    return http.post<Workflow>(`/workflows/${id}/edit`, {});
  },

  cancelEdit(id: string) {
    // Discards the current draft and restores the latest deployed
    // version. Backend 400s if there's no prior deploy to fall back on.
    return http.post<Workflow>(`/workflows/${id}/cancel-edit`, {});
  },

  listVersions(id: string) {
    return http.get<WorkflowVersionData[]>(`/workflows/${id}/versions`);
  },

  listRuns(
    id: string,
    opts: {
      runType?: "draft" | "deployed";
      includeDrafts?: boolean;
      offset?: number; limit?: number;
      versionId?: string;
    } = {},
  ) {
    const params = new URLSearchParams();
    if (opts.runType) params.set("run_type", opts.runType);
    if (opts.includeDrafts) params.set("include_drafts", "true");
    if (opts.offset !== undefined) params.set("offset", String(opts.offset));
    if (opts.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts.versionId) params.set("version_id", opts.versionId);
    const qs = params.toString();
    return http.get<WorkflowRunListResponse>(
      `/workflows/${id}/runs${qs ? `?${qs}` : ""}`,
    );
  },

  getRun(id: string, runId: string) {
    return http.get<WorkflowRun>(`/workflows/${id}/runs/${runId}`);
  },

  triggerRun(
    id: string,
    opts: { runType?: "draft" | "deployed"; triggerData?: Record<string, unknown> } = {},
  ) {
    return http.post<WorkflowRun>(`/workflows/${id}/runs`, {
      run_type: opts.runType ?? "draft",
      trigger_type: "manual",
      trigger_data: opts.triggerData ?? {},
    });
  },

  cancelRun(id: string, runId: string) {
    return http.post(`/workflows/${id}/runs/${runId}/cancel`, {});
  },

  resumeRun(id: string, runId: string) {
    return http.post<WorkflowRun>(`/workflows/${id}/runs/${runId}/resume`, {});
  },

  async assistantStream(
    id: string,
    data: {
      user_message: string;
      current_definition: { nodes: unknown[]; edges: unknown[] };
      history: { role: "user" | "assistant"; content: string }[];
    },
    callbacks: AssistantStreamCallbacks,
  ): Promise<void> {
    const res = await fetch(`/api/workflows/${id}/assistant/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal: callbacks.signal,
    });
    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || `Assistant request failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames separated by blank line
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of frame.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          try {
            callbacks.onEvent(JSON.parse(payload) as AssistantStreamEvent);
          } catch {
            // Skip malformed frames
          }
        }
      }
    }
  },
};

import { http } from "@/lib/http";
import type { Workflow, WorkflowRun } from "@/types";

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
  visibility?: string;
}

export interface WorkflowUpdateData {
  name?: string;
  description?: string;
  definition?: Record<string, unknown>;
  model_config?: { backend: string; model: string };
  visibility?: string;
}

export interface WorkflowVersionData {
  id: string;
  version: number;
  deployed_by: string;
  deployed_at: string;
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

  listVersions(id: string) {
    return http.get<WorkflowVersionData[]>(`/workflows/${id}/versions`);
  },

  listRuns(id: string) {
    return http.get<WorkflowRunListResponse>(`/workflows/${id}/runs`);
  },

  getRun(id: string, runId: string) {
    return http.get<WorkflowRun>(`/workflows/${id}/runs/${runId}`);
  },

  triggerRun(id: string, triggerData: Record<string, unknown> = {}) {
    return http.post<WorkflowRun>(`/workflows/${id}/runs`, {
      trigger_type: "manual",
      trigger_data: triggerData,
    });
  },

  cancelRun(id: string, runId: string) {
    return http.post(`/workflows/${id}/runs/${runId}/cancel`, {});
  },
};

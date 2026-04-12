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
  visibility?: string;
}

export interface WorkflowUpdateData {
  name?: string;
  description?: string;
  definition?: Record<string, unknown>;
  visibility?: string;
  status?: string;
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

  listRuns(id: string) {
    return http.get<WorkflowRunListResponse>(`/workflows/${id}/runs`);
  },

  getRun(id: string, runId: string) {
    return http.get<WorkflowRun>(`/workflows/${id}/runs/${runId}`);
  },
};

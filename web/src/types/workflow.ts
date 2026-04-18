import type { ModelConfig } from "./agent";

export interface Workflow {
  id: string;
  name: string;
  slug: string;
  description?: string;
  owner_id: string;
  definition: WorkflowDefinition;
  model_config: ModelConfig;
  status: "draft" | "deployed";
  current_version?: number | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport: { x: number; y: number; zoom: number };
}

export interface WorkflowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  data?: Record<string, unknown>;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  version_id?: string | null;
  run_type: "draft" | "deployed";
  triggered_by: string;
  trigger_type: string;
  trigger_data?: Record<string, unknown>;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  started_at?: string;
  completed_at?: string;
  error?: string;
  created_at: string;
  /** Only populated on `GET /workflows/{id}/runs/{runId}`; list endpoints
   *  return null so payloads stay small. */
  node_runs?: WorkflowNodeRun[] | null;
}

export interface WorkflowNodeRun {
  id: string;
  node_id: string;
  node_type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  input_data?: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
  error?: string;
  /** For agent_step nodes: the chat session the inspector subscribes to
   *  for history + live stream. Null for non-agent_step nodes. */
  session_id?: string | null;
}

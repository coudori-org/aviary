import type { Node, Edge } from "@xyflow/react";

// --- Node data types ---

export interface ManualTriggerData {
  label: string;
  [key: string]: unknown;
}

export interface WebhookTriggerData {
  label: string;
  path: string;
  [key: string]: unknown;
}

export interface StructuredOutputField {
  name: string;
  type: "str" | "list";
  description?: string;
}

export interface ArtifactField {
  name: string;
  description?: string;
}

export interface AgentStepData {
  label: string;
  instruction: string;
  model_config: { backend: string; model: string; max_output_tokens?: number };
  mcp_tool_ids: string[];
  prompt_template: string;
  // Extra fields appended to the default `text` output. Runtime gets
  // `[{name:"text",...}, ...structured_output_fields]` as the schema, so
  // `text` is always present and users only manage the extras.
  structured_output_fields?: StructuredOutputField[];
  // Named file/directory outputs. When set, the runtime exposes
  // `save_as_artifact` to the agent; downstream steps receive each produced
  // artifact as `/workspace/{name}` inside their sandbox.
  artifacts?: ArtifactField[];
  [key: string]: unknown;
}

export interface ConditionData {
  label: string;
  expression: string;
  [key: string]: unknown;
}

export interface MergeData {
  label: string;
  [key: string]: unknown;
}

export interface PayloadParserData {
  label: string;
  mapping: Record<string, string>;
  [key: string]: unknown;
}

export interface TemplateData {
  label: string;
  template: string;
  [key: string]: unknown;
}

export type NodeData =
  | ManualTriggerData
  | WebhookTriggerData
  | AgentStepData
  | ConditionData
  | MergeData
  | PayloadParserData
  | TemplateData;

// Workflow node types (React Flow node type key)
export const NODE_TYPES = [
  "manual_trigger",
  "webhook_trigger",
  "agent_step",
  "condition",
  "merge",
  "payload_parser",
  "template",
] as const;

export type NodeType = (typeof NODE_TYPES)[number];

// React Flow typed aliases
export type WorkflowNode = Node<NodeData, NodeType>;
export type WorkflowEdge = Edge;

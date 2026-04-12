import type { NodeType, NodeData } from "./types";

export interface NodeDefinition {
  type: NodeType;
  label: string;
  category: "trigger" | "agent" | "transform" | "control";
  defaultData: NodeData;
}

export const NODE_REGISTRY: NodeDefinition[] = [
  {
    type: "manual_trigger",
    label: "Manual Trigger",
    category: "trigger",
    defaultData: { label: "Manual Trigger" },
  },
  {
    type: "webhook_trigger",
    label: "Webhook Trigger",
    category: "trigger",
    defaultData: { label: "Webhook Trigger", path: "/webhook" },
  },
  {
    type: "agent_step",
    label: "Agent Step",
    category: "agent",
    defaultData: {
      label: "Agent Step",
      instruction: "",
      model_config: { backend: "", model: "" },
      mcp_tool_ids: [],
      prompt_template: "{{input}}",
    },
  },
  {
    type: "condition",
    label: "Condition",
    category: "control",
    defaultData: { label: "Condition", expression: "" },
  },
  {
    type: "merge",
    label: "Merge",
    category: "control",
    defaultData: { label: "Merge" },
  },
  {
    type: "payload_parser",
    label: "Payload Parser",
    category: "transform",
    defaultData: { label: "Payload Parser", mapping: {} },
  },
  {
    type: "template",
    label: "Template",
    category: "transform",
    defaultData: { label: "Template", template: "" },
  },
];

export const NODE_CATEGORIES = [
  { key: "trigger", label: "Triggers" },
  { key: "agent", label: "Agent" },
  { key: "control", label: "Control" },
  { key: "transform", label: "Transform" },
] as const;

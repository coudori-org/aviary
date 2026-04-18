export interface Session {
  id: string;
  agent_id: string | null;
  type: "private" | "team";
  created_by: string;
  team_id?: string;
  title?: string;
  status: "active" | "archived";
  pod_name?: string;
  last_message_at?: string;
  created_at: string;
  /** Workflow-origin session: anchored to a workflow run's root run id
   *  (for resume-chain continuity) rather than a chat agent. Null for
   *  regular chat sessions. */
  workflow_run_id?: string | null;
  /** Workflow node this session belongs to. */
  node_id?: string | null;
}

export interface Message {
  id: string;
  session_id: string;
  sender_type: "user" | "agent";
  sender_id?: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

// --- Streaming block types ---

export interface TextBlock {
  type: "text";
  id: string;
  content: string;
}

export interface ToolCallBlock {
  type: "tool_call";
  id: string;
  name: string;
  input: Record<string, unknown>;
  status: "running" | "complete";
  result?: string;
  is_error?: boolean;
  elapsed?: number;
  parent_tool_use_id?: string;
  children?: StreamBlock[];
}

export interface ThinkingBlock {
  type: "thinking";
  id: string;
  content: string;
}

export interface ErrorBlock {
  type: "error";
  id: string;
  message: string;
}

export type StreamBlock = TextBlock | ToolCallBlock | ThinkingBlock | ErrorBlock;

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

// --- File attachments ---

export interface FileRef {
  file_id: string;
  filename: string;
  content_type: string;
}

export interface PendingAttachment {
  localId: string;
  file: File;
  preview: string;
  status: "uploading" | "done" | "error";
  fileRef?: FileRef;
}

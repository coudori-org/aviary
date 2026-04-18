"use client";

import Link from "next/link";
import { ArrowLeft, Pencil, Printer, FileText } from "@/components/icons";
import { routes } from "@/lib/constants/routes";
import { STATUS_LABELS } from "./chat-status-banner";
import { ChatWidthToggle } from "./chat-width-toggle";
import type { ConnectionStatus } from "@/lib/ws";
import type { Session } from "@/types";
import { useTitleEditor } from "@/features/chat/hooks/use-title-editor";
import { useChatWidth } from "@/features/chat/hooks/use-chat-width";
import { cn } from "@/lib/utils";

const STATUS_DOT: Record<ConnectionStatus, string> = {
  connecting: "bg-warning animate-pulse-soft",
  provisioning: "bg-warning animate-pulse-soft",
  spawning: "bg-warning animate-pulse-soft",
  waiting: "bg-warning animate-pulse-soft",
  ready: "bg-success",
  offline: "bg-danger",
  disconnected: "bg-fg-disabled",
  reconnecting: "bg-warning animate-pulse-soft",
};

const STATUS_TEXT: Record<ConnectionStatus, string> = {
  connecting: "text-warning",
  provisioning: "text-warning",
  spawning: "text-warning",
  waiting: "text-warning",
  ready: "text-success",
  offline: "text-danger",
  disconnected: "text-fg-muted",
  reconnecting: "text-warning",
};

interface ChatHeaderProps {
  session: Session;
  status: ConnectionStatus;
  hasMessages: boolean;
  onPrintVisual: () => void;
  onExportText: () => void;
  titleEditor: ReturnType<typeof useTitleEditor>;
}

/**
 * ChatHeader — top bar with back button, inline title editor, export
 * actions, and connection-status pill.
 */
export function ChatHeader({
  session,
  status,
  hasMessages,
  onPrintVisual,
  onExportText,
  titleEditor,
}: ChatHeaderProps) {
  const { isEditing, draft, setDraft, inputRef, startEditing, save, handleKeyDown } = titleEditor;
  const { widthClass } = useChatWidth();

  return (
    <header className="shrink-0 border-b border-white/[0.06] px-6 py-3">
      <div className={cn("mx-auto flex items-center justify-between", widthClass)}>
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href={session.agent_id ? routes.agent(session.agent_id) : routes.agents}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm bg-raised text-fg-muted hover:text-fg-primary transition-colors"
            aria-label="Back to agent"
          >
            <ArrowLeft size={14} strokeWidth={1.75} />
          </Link>

          {isEditing ? (
            <input
              ref={inputRef}
              className="type-button text-fg-primary bg-transparent border-b border-info outline-none w-[500px] max-w-[60vw]"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={save}
              onKeyDown={handleKeyDown}
              maxLength={200}
            />
          ) : (
            <button
              type="button"
              className="group flex items-center gap-1.5 type-button text-fg-primary hover:opacity-80 transition-opacity min-w-0"
              onClick={startEditing}
            >
              <span className="truncate">{session.title || "New Session"}</span>
              <Pencil
                size={11}
                strokeWidth={2}
                className="shrink-0 text-fg-disabled group-hover:text-fg-muted transition-colors"
              />
            </button>
          )}
        </div>

        <div className="flex items-center gap-3">
          <ChatWidthToggle />

          <button
            type="button"
            onClick={onPrintVisual}
            disabled={!hasMessages}
            className="flex h-7 w-7 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors disabled:opacity-30 disabled:pointer-events-none"
            title="Print chat"
            aria-label="Print chat"
          >
            <Printer size={14} strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={onExportText}
            disabled={!hasMessages}
            className="flex h-7 w-7 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors disabled:opacity-30 disabled:pointer-events-none"
            title="Export chat as text"
            aria-label="Export chat as text"
          >
            <FileText size={14} strokeWidth={1.75} />
          </button>

          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2 w-2 rounded-full transition-colors duration-300",
                STATUS_DOT[status],
              )}
            />
            <span
              className={cn(
                "type-caption transition-colors duration-300",
                STATUS_TEXT[status],
              )}
            >
              {STATUS_LABELS[status]}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

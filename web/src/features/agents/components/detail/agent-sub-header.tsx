"use client";

import * as React from "react";
import Link from "next/link";
import { FileText, Pencil, Printer, Wrench, PanelRight, PanelRightClose } from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { useChatActions } from "@/features/chat/hooks/chat-actions-context";
import { ChatWidthToggle } from "@/features/chat/components/chat-width-toggle";
import { toneFromId, initialFromName } from "@/lib/tone";
import { routes } from "@/lib/constants/routes";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types";

export interface AgentSubHeaderProps {
  agent: Agent;
  /** Optional workspace rail toggle — only shown when handler provided. */
  workspaceOpen?: boolean;
  onToggleWorkspace?: () => void;
}

/**
 * One-line agent identity row that sits directly under the AppShell
 * breadcrumb. Holds the visual identity (tone avatar, description,
 * model/tools chips) plus the Edit shortcut so the chat pane below
 * stays full height.
 */
export function AgentSubHeader({
  agent,
  workspaceOpen,
  onToggleWorkspace,
}: AgentSubHeaderProps) {
  const tone = toneFromId(agent.id);
  const toolCount = (agent.tools?.length ?? 0) + (agent.mcp_servers?.length ?? 0);
  const model = agent.model_config?.model ?? agent.model_config?.backend ?? "—";
  const chatActions = useChatActions();
  return (
    <div
      className={cn(
        "flex items-center gap-3 border-b border-border-subtle bg-canvas",
        "h-[44px] px-4"
      )}
    >
      <Link
        href={routes.agentDetail(agent.id)}
        className={cn(
          "group flex shrink-0 items-center gap-2",
          "rounded-[7px] px-1 -mx-1 py-0.5 -my-0.5",
          "transition-colors duration-fast hover:bg-hover"
        )}
        title="Open agent detail"
      >
        <Avatar tone={tone} size="md">
          {agent.icon || initialFromName(agent.name)}
        </Avatar>
        <span className="t-h3 fg-primary truncate group-hover:underline decoration-fg-muted underline-offset-2">
          {agent.name}
        </span>
      </Link>

      {chatActions ? (
        <SessionTitle
          sessionTitle={chatActions.sessionTitle}
          onSave={chatActions.saveTitle}
        />
      ) : agent.description?.trim() ? (
        <span className="hidden min-w-0 flex-1 truncate text-[12px] text-fg-tertiary sm:inline">
          {agent.description}
        </span>
      ) : (
        <div className="flex-1" />
      )}

      {!chatActions && (
        <Chip>
          <span className="t-mono">{model}</span>
        </Chip>
      )}
      {!chatActions && (
        <Chip>
          <Wrench size={11} />
          <span className="num t-mono">{toolCount}</span>
          <span className="text-fg-muted">tools</span>
        </Chip>
      )}

      {chatActions && (
        <>
          <ChatWidthToggle />
          <IconBtn
            disabled={!chatActions.hasMessages}
            onClick={chatActions.onPrintVisual}
            title="Print chat"
            aria-label="Print chat"
          >
            <Printer size={13} />
          </IconBtn>
          <IconBtn
            disabled={!chatActions.hasMessages}
            onClick={chatActions.onExportText}
            title="Export chat as text"
            aria-label="Export chat as text"
          >
            <FileText size={13} />
          </IconBtn>
        </>
      )}

      <Button asChild variant="outline" size="sm">
        <Link href={routes.agentEdit(agent.id)}>
          <Pencil size={12} /> Edit
        </Link>
      </Button>
      {onToggleWorkspace && (
        <button
          type="button"
          onClick={onToggleWorkspace}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-[6px]",
            "text-fg-secondary transition-colors duration-fast",
            workspaceOpen ? "bg-hover text-fg-primary" : "hover:bg-hover hover:text-fg-primary"
          )}
          aria-label={workspaceOpen ? "Hide workspace" : "Show workspace"}
          aria-pressed={workspaceOpen}
          title={workspaceOpen ? "Hide workspace" : "Show workspace"}
        >
          {workspaceOpen ? <PanelRightClose size={14} /> : <PanelRight size={14} />}
        </button>
      )}
    </div>
  );

}

/**
 * Owns its own draft / isEditing / inputRef so a parent re-render (e.g.
 * ChatActions republish on each keystroke) can't reset the IME composition
 * mid-character. The outer `onSave` callback only fires on commit (Enter
 * or blur), never on every keystroke.
 */
function SessionTitle({
  sessionTitle,
  onSave,
}: {
  sessionTitle: string | null;
  onSave: (next: string) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);
  const composingRef = React.useRef(false);

  const startEditing = React.useCallback(() => {
    setDraft(sessionTitle ?? "");
    setIsEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [sessionTitle]);

  const commit = React.useCallback(async () => {
    setIsEditing(false);
    try {
      await onSave(draft);
    } catch {
      // Optimistic revert is handled inside onSave; nothing to do here.
    }
  }, [draft, onSave]);

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (composingRef.current || e.nativeEvent.isComposing) return;
      if (e.key === "Enter") {
        e.preventDefault();
        e.currentTarget.blur();
      } else if (e.key === "Escape") {
        setIsEditing(false);
      }
    },
    [],
  );

  return (
    <div className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className="text-fg-muted">/</span>
      {isEditing ? (
        <input
          ref={inputRef}
          className={cn(
            "min-w-0 flex-1 max-w-[480px] bg-transparent text-[13px] text-fg-primary",
            "border-b border-accent outline-none"
          )}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onCompositionStart={() => {
            composingRef.current = true;
          }}
          onCompositionEnd={() => {
            composingRef.current = false;
          }}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          maxLength={200}
        />
      ) : (
        <button
          type="button"
          onClick={startEditing}
          className={cn(
            "group inline-flex min-w-0 items-center gap-1.5 rounded-[6px] px-1.5 -mx-1.5 py-0.5",
            "text-[13px] text-fg-primary hover:bg-hover transition-colors"
          )}
          title="Edit session title"
        >
          <span className="truncate">{sessionTitle || "New session"}</span>
          <Pencil
            size={11}
            strokeWidth={2}
            className="shrink-0 text-fg-muted group-hover:text-fg-secondary transition-colors"
          />
        </button>
      )}
    </div>
  );
}

function IconBtn({
  children,
  disabled,
  onClick,
  title,
  ...rest
}: {
  children: React.ReactNode;
  disabled?: boolean;
  onClick: () => void;
  title?: string;
  "aria-label"?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      {...rest}
      className={cn(
        "inline-flex h-7 w-7 items-center justify-center rounded-[6px]",
        "text-fg-tertiary transition-colors duration-fast",
        "hover:bg-hover hover:text-fg-primary",
        "disabled:opacity-30 disabled:pointer-events-none"
      )}
    >
      {children}
    </button>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 h-[22px] px-2 rounded-[5px]",
        "bg-hover text-[11.5px] text-fg-secondary"
      )}
    >
      {children}
    </span>
  );
}

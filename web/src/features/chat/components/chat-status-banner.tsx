"use client";

import { Spinner } from "@/components/ui/spinner";
import { useChatWidth } from "@/features/chat/hooks/use-chat-width";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "@/lib/ws";

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: "Connecting",
  provisioning: "Setting up environment",
  spawning: "Starting agent",
  waiting: "Almost ready",
  ready: "Online",
  offline: "Offline",
  disconnected: "Disconnected",
  reconnecting: "Reconnecting",
};

interface ChatStatusBannerProps {
  status: ConnectionStatus;
  statusMessage: string | null;
  showConnecting: boolean;
  /** Seconds until next reconnect attempt (null when not in backoff) */
  reconnectIn: number | null;
  /** Bypass the backoff and try immediately */
  onRetryNow: () => void;
}

/**
 * ChatStatusBanner — slim banner above the message list showing connection
 * state when not ready. Variants:
 *   - intermediate connecting (warning, spinner) — debounced 500ms
 *   - reconnecting (warning, spinner, countdown, [Retry now] button)
 *   - offline (danger)
 *   - disconnected — should be transient now that auto-reconnect runs;
 *     kept as a fallback for edge cases
 */
export function ChatStatusBanner({
  status,
  statusMessage,
  showConnecting,
  reconnectIn,
  onRetryNow,
}: ChatStatusBannerProps) {
  const { widthClass } = useChatWidth();

  if (status === "reconnecting") {
    return (
      <div className="shrink-0 border-b border-warning/10 bg-warning/[0.04] px-6 py-2.5 animate-fade-in">
        <div className={cn("mx-auto flex items-center justify-center gap-2", widthClass)}>
          <Spinner size={14} className="text-warning" />
          <span className="type-caption text-warning">
            {reconnectIn != null
              ? `Reconnecting in ${reconnectIn}s…`
              : "Reconnecting…"}
          </span>
          <button
            type="button"
            onClick={onRetryNow}
            className="ml-1 rounded-xs px-2 py-0.5 type-caption-bold text-warning underline underline-offset-2 hover:opacity-80 transition-opacity"
          >
            Retry now
          </button>
        </div>
      </div>
    );
  }

  if (showConnecting) {
    return (
      <div className="shrink-0 border-b border-warning/10 bg-warning/[0.04] px-6 py-2.5 animate-fade-in">
        <div className={cn("mx-auto flex items-center justify-center gap-2", widthClass)}>
          <Spinner size={14} className="text-warning" />
          <span className="type-caption text-warning">
            {STATUS_LABELS[status]}
            {statusMessage && ` — ${statusMessage}`}
          </span>
        </div>
      </div>
    );
  }

  if (status === "offline") {
    return (
      <div className="shrink-0 border-b border-danger/10 bg-danger/[0.04] px-6 py-2.5">
        <div className={cn("mx-auto flex items-center justify-center", widthClass)}>
          <span className="type-caption text-danger">
            Agent is offline{statusMessage && ` — ${statusMessage}`}
          </span>
        </div>
      </div>
    );
  }

  if (status === "disconnected") {
    return (
      <div className="shrink-0 border-b border-white/[0.06] bg-raised/50 px-6 py-2.5">
        <div className={cn("mx-auto flex items-center justify-center gap-2", widthClass)}>
          <span className="type-caption text-fg-muted">Connection lost.</span>
          <button
            type="button"
            onClick={onRetryNow}
            className="rounded-xs px-2 py-0.5 type-caption-bold text-info underline underline-offset-2 hover:opacity-80 transition-opacity"
          >
            Reconnect
          </button>
        </div>
      </div>
    );
  }

  return null;
}

export { STATUS_LABELS };

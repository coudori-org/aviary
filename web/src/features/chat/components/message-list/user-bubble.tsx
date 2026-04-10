"use client";

import { useChatSearchTargetId } from "@/features/chat/hooks/chat-search-context";
import { cn } from "@/lib/utils";

interface UserBubbleProps {
  content: string;
  /** When false, render an invisible spacer in the avatar slot so the
   *  bubble stays horizontally aligned with the run's first message. */
  showAvatar?: boolean;
  /** `data-search-target` for in-chat search ring + scroll. */
  targetId: string;
}

/**
 * UserBubble — right-aligned user message with brand-tinted background.
 * Pure presentation, no markdown rendering (user input is plain text).
 *
 * Width is constrained to 60% (vs 88% for agent) — user messages are
 * usually short prompts and the asymmetry creates a more natural rhythm
 * than equal-width bubbles on both sides.
 */
export function UserBubble({ content, showAvatar = true, targetId }: UserBubbleProps) {
  const activeTargetId = useChatSearchTargetId();
  const isActiveMatch = activeTargetId === targetId;

  return (
    <div className="flex flex-row-reverse gap-3 group animate-fade-in">
      {showAvatar ? (
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-info/15 type-small text-info">
          You
        </div>
      ) : (
        <div className="h-8 w-8 shrink-0" aria-hidden="true" />
      )}
      <div
        data-search-target={targetId}
        className={cn(
          "max-w-[60%] rounded-xl rounded-tr-sm transition-shadow",
          isActiveMatch &&
            "ring-2 ring-info/60 ring-offset-2 ring-offset-canvas",
        )}
      >
        <div className="rounded-xl rounded-tr-sm bg-info/10 px-4 py-3 type-body text-fg-primary">
          <div className="whitespace-pre-wrap break-words">{content}</div>
        </div>
      </div>
    </div>
  );
}

"use client";

import {
  forwardRef,
  Fragment,
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
} from "react";
import { MessageBubble } from "./message-bubble";
import { TimeDivider } from "./time-divider";
import { RestartDivider } from "./restart-divider";
import { JumpRail } from "./jump-rail";
import { StreamingResponse } from "@/features/chat/components/blocks/streaming-response";
import { ChatEmptyState } from "@/features/chat/components/chat-empty-state";
import { Spinner } from "@/components/ui/spinner";
import { computeTimeDividerLabel } from "@/features/chat/lib/relative-time";
import { useChatWidth } from "@/features/chat/hooks/use-chat-width";
import { highlightText, clearHighlights } from "@/features/chat/lib/highlight-text";
import { cn } from "@/lib/utils";
import type { Message, StreamBlock } from "@/types";

const PRELOAD_THRESHOLD_PX = 1500;
const FOLLOW_THRESHOLD_PX = 80;

interface MessageListProps {
  messages: Message[];
  blocks: StreamBlock[];
  isStreaming: boolean;
  isReady: boolean;
  hasMore: boolean;
  loadingEarlier: boolean;
  onLoadEarlier: () => void;
  highlightedTargetId?: string | null;
  searchQuery?: string;
  /** Insert a divider between a terminal (error / cancelled) agent turn
   *  and the next user turn — workflow agent_step sessions where resume
   *  starts a fresh SDK context. Chat sessions preserve history, so off
   *  by default. */
  showRestartDividers?: boolean;
}

export const MessageList = forwardRef<HTMLDivElement, MessageListProps>(
  function MessageList(
    {
      messages,
      blocks,
      isStreaming,
      isReady,
      hasMore,
      loadingEarlier,
      onLoadEarlier,
      highlightedTargetId,
      searchQuery,
      showRestartDividers = false,
    },
    forwardedRef,
  ) {
    const scrollRef = useRef<HTMLDivElement>(null);
    useImperativeHandle(forwardedRef, () => scrollRef.current as HTMLDivElement);
    const { widthClass } = useChatWidth();

    useEffect(() => {
      if (!highlightedTargetId) return;
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      const el = scrollEl.querySelector(
        `[data-search-target="${CSS.escape(highlightedTargetId)}"]`,
      ) as HTMLElement | null;
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, [highlightedTargetId, messages]);

    useEffect(() => {
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      if (!searchQuery) {
        clearHighlights(scrollEl);
        return;
      }

      let raf = 0;
      const reapply = () => {
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          clearHighlights(scrollEl);
          highlightText(scrollEl, searchQuery);
        });
      };
      reapply();

      const inner = scrollEl.firstElementChild;
      if (!inner) return;
      const observer = new ResizeObserver(reapply);
      observer.observe(inner);
      return () => {
        if (raf) cancelAnimationFrame(raf);
        observer.disconnect();
        clearHighlights(scrollEl);
      };
    }, [searchQuery, messages]);

    const prevFirstIdRef = useRef<string | null>(null);
    const prevLastIdRef = useRef<string | null>(null);
    const prevScrollHeightRef = useRef(0);
    const didInitialScrollRef = useRef(false);
    // Log-viewer follow mode — auto-scroll only when the user is at the
    // bottom; disengaged once they scroll up to read history.
    const followRef = useRef(true);

    useLayoutEffect(() => {
      const el = scrollRef.current;
      if (!el) return;
      const firstId = messages[0]?.id ?? null;
      const lastId = messages[messages.length - 1]?.id ?? null;
      const prevFirst = prevFirstIdRef.current;
      const prevLast = prevLastIdRef.current;

      prevFirstIdRef.current = firstId;
      prevLastIdRef.current = lastId;
      const prevScrollHeight = prevScrollHeightRef.current;
      prevScrollHeightRef.current = el.scrollHeight;

      if (!didInitialScrollRef.current && messages.length > 0) {
        el.scrollTop = el.scrollHeight;
        didInitialScrollRef.current = true;
        // Re-scroll after lazy images settle so we land at the true bottom.
        const images = el.querySelectorAll("img");
        if (images.length > 0) {
          let pending = 0;
          const rescroll = () => { el.scrollTop = el.scrollHeight; };
          images.forEach((img) => {
            if (!img.complete) {
              pending++;
              img.addEventListener("load", () => { if (--pending === 0) rescroll(); }, { once: true });
              img.addEventListener("error", () => { if (--pending === 0) rescroll(); }, { once: true });
            }
          });
        }
        return;
      }
      if (prevFirst !== null && firstId !== prevFirst && lastId === prevLast) {
        // Prepend — pin viewport regardless of follow mode.
        el.scrollTop += el.scrollHeight - prevScrollHeight;
        return;
      }
      if (prevLast !== null && lastId !== prevLast && followRef.current) {
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      }
    }, [messages]);

    useEffect(() => {
      if (blocks.length === 0) return;
      if (!followRef.current) return;
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }, [blocks]);

    const loadEarlierRef = useRef(onLoadEarlier);
    const hasMoreRef = useRef(hasMore);
    const loadingEarlierRef = useRef(loadingEarlier);
    useEffect(() => {
      loadEarlierRef.current = onLoadEarlier;
      hasMoreRef.current = hasMore;
      loadingEarlierRef.current = loadingEarlier;
    });

    useEffect(() => {
      const el = scrollRef.current;
      if (!el) return;
      const onScroll = () => {
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        followRef.current = distFromBottom <= FOLLOW_THRESHOLD_PX;
        if (hasMoreRef.current && !loadingEarlierRef.current && el.scrollTop < PRELOAD_THRESHOLD_PX) {
          loadEarlierRef.current();
        }
      };
      el.addEventListener("scroll", onScroll, { passive: true });
      return () => el.removeEventListener("scroll", onScroll);
    }, []);

    // Chain prepends so successive small pages stream in without the
    // "Loading earlier" affordance flashing between each one.
    useEffect(() => {
      if (!hasMore || loadingEarlier) return;
      const el = scrollRef.current;
      if (!el) return;
      if (el.scrollTop < PRELOAD_THRESHOLD_PX) {
        onLoadEarlier();
      }
    }, [messages, hasMore, loadingEarlier, onLoadEarlier]);

    const handleLoadEarlierClick = useCallback(() => {
      if (!hasMore || loadingEarlier) return;
      onLoadEarlier();
    }, [hasMore, loadingEarlier, onLoadEarlier]);

    return (
      <div className="relative flex-1 min-h-0">
        <div
          ref={scrollRef}
          className="absolute inset-0 overflow-y-auto"
          // Disable browser scroll anchoring so the prepend layout effect
          // isn't double-corrected.
          style={{ overflowAnchor: "none" }}
        >
          <div className={cn("mx-auto px-6 py-6", widthClass)}>
            {hasMore && (
              <div className="mb-4 flex justify-center">
                <button
                  type="button"
                  onClick={handleLoadEarlierClick}
                  disabled={loadingEarlier}
                  className="flex items-center gap-2 rounded-sm px-3 py-1.5 type-caption text-fg-muted hover:text-fg-primary disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loadingEarlier ? (
                    <>
                      <Spinner size={12} />
                      <span>Loading earlier messages…</span>
                    </>
                  ) : (
                    <span>Show earlier messages</span>
                  )}
                </button>
              </div>
            )}

            {messages.length === 0 && isReady && !isStreaming && <ChatEmptyState />}

            <div className="space-y-5">
              {messages.map((msg, idx) => {
                const prev = idx > 0 ? messages[idx - 1] : null;
                const dividerLabel = prev
                  ? computeTimeDividerLabel(prev.created_at, msg.created_at)
                  : null;
                const prevTerminated =
                  !!prev?.metadata?.error || !!prev?.metadata?.cancelled;
                const showRestart =
                  showRestartDividers &&
                  !!prev &&
                  prev.sender_type === "agent" &&
                  prevTerminated &&
                  msg.sender_type === "user";
                const showAvatar =
                  !prev || prev.sender_type !== msg.sender_type || dividerLabel !== null || showRestart;

                return (
                  <Fragment key={msg.id}>
                    {showRestart && <RestartDivider />}
                    {dividerLabel && <TimeDivider label={dividerLabel} />}
                    <div
                      data-rail-id={msg.id}
                      data-rail-kind={
                        msg.sender_type === "user"
                          ? "user"
                          : msg.metadata?.error
                            ? "tool-error"
                            : "agent"
                      }
                      data-rail-preview={
                        msg.content.split("\n")[0].slice(0, 100) || "(no text)"
                      }
                    >
                      <MessageBubble message={msg} showAvatar={showAvatar} />
                    </div>
                  </Fragment>
                );
              })}

              {(blocks.length > 0 || isStreaming) && (
                <StreamingResponse blocks={blocks} isStreaming={isStreaming} />
              )}
            </div>
          </div>
        </div>
        <JumpRail messageCount={messages.length} scrollRef={scrollRef} />
      </div>
    );
  },
);

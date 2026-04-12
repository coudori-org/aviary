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
import { JumpRail } from "./jump-rail";
import { StreamingResponse } from "@/features/chat/components/blocks/streaming-response";
import { ChatEmptyState } from "@/features/chat/components/chat-empty-state";
import { Spinner } from "@/components/ui/spinner";
import { computeTimeDividerLabel } from "@/features/chat/lib/relative-time";
import { useChatWidth } from "@/features/chat/hooks/use-chat-width";
import { highlightText, clearHighlights } from "@/features/chat/lib/highlight-text";
import { cn } from "@/lib/utils";
import type { Message, StreamBlock } from "@/types";

/** Distance from the top at which older messages start pre-loading. */
const PRELOAD_THRESHOLD_PX = 1500;

interface MessageListProps {
  messages: Message[];
  blocks: StreamBlock[];
  isStreaming: boolean;
  isReady: boolean;
  hasMore: boolean;
  loadingEarlier: boolean;
  onLoadEarlier: () => void;
  /** Block id of the active in-chat search match. The list scrolls
   *  the matching `[data-search-target]` element into view; the ring
   *  is painted by the block component via the search context. */
  highlightedTargetId?: string | null;
  /** Live search query. When non-empty, the list inserts `<mark>`
   *  spans around every occurrence in the rendered DOM. */
  searchQuery?: string;
}

/**
 * MessageList — scrollable message container with paginated history.
 *
 * Scroll behaviors (resolved in one layout effect via first/last id diff):
 *   - initial mount → jump to bottom
 *   - append (last id changed) → smooth-scroll to bottom
 *   - prepend (first id changed, last unchanged) → adjust scrollTop by the
 *     height diff so the viewport anchor stays put
 *
 * Pre-fetch fires when within `PRELOAD_THRESHOLD_PX` of the top, both on
 * scroll and after a prepend (so back-to-back pages chain without flash).
 */
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
    },
    forwardedRef,
  ) {
    const scrollRef = useRef<HTMLDivElement>(null);
    useImperativeHandle(forwardedRef, () => scrollRef.current as HTMLDivElement);
    const { widthClass } = useChatWidth();

    // Scroll the active search target into view. Re-runs on `messages`
    // so a target that just arrived via paginated prepend lands too.
    useEffect(() => {
      if (!highlightedTargetId) return;
      const scrollEl = scrollRef.current;
      if (!scrollEl) return;
      const el = scrollEl.querySelector(
        `[data-search-target="${CSS.escape(highlightedTargetId)}"]`,
      ) as HTMLElement | null;
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, [highlightedTargetId, messages]);

    // DOM-walk text highlighter. ResizeObserver re-applies on content
    // reflow (prepend, tool group expand) — marks are inline so they
    // don't feedback-loop into the observer.
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
        // Images may not be loaded yet — re-scroll after they finish.
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
        // Prepend — keep the viewport anchor pinned.
        el.scrollTop += el.scrollHeight - prevScrollHeight;
        return;
      }
      if (prevLast !== null && lastId !== prevLast) {
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      }
    }, [messages]);

    // Streaming block updates always scroll to bottom (they only extend
    // the current in-flight response — never a prepend).
    useEffect(() => {
      if (blocks.length === 0) return;
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }, [blocks]);

    // Refs for the live values used inside the scroll listener (which is
    // attached once and shouldn't re-subscribe on every render).
    const loadEarlierRef = useRef(onLoadEarlier);
    const hasMoreRef = useRef(hasMore);
    const loadingEarlierRef = useRef(loadingEarlier);
    useEffect(() => {
      loadEarlierRef.current = onLoadEarlier;
      hasMoreRef.current = hasMore;
      loadingEarlierRef.current = loadingEarlier;
    });

    // Scroll-driven pre-fetch: fires whenever the user gets within
    // PRELOAD_THRESHOLD_PX of the top.
    useEffect(() => {
      const el = scrollRef.current;
      if (!el) return;
      const onScroll = () => {
        if (!hasMoreRef.current || loadingEarlierRef.current) return;
        if (el.scrollTop < PRELOAD_THRESHOLD_PX) {
          loadEarlierRef.current();
        }
      };
      el.addEventListener("scroll", onScroll, { passive: true });
      return () => el.removeEventListener("scroll", onScroll);
    }, []);

    // Chain effect: after a successful prepend, if the new scrollTop is
    // STILL within the preload zone, immediately request the next page.
    // This lets several small pages stream in back-to-back without the
    // user ever seeing the "Loading earlier messages…" affordance flash.
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
          // Disable browser scroll anchoring so the layout effect's manual
          // scrollTop adjust isn't double-corrected on prepend.
          style={{ overflowAnchor: "none" }}
        >
          <div className={cn("mx-auto px-6 py-6", widthClass)}>
            {/* Manual pagination affordance. Auto pre-fetch usually
                covers it, but the button stays as an explicit fallback
                and a visible signal that more history exists. */}
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
                // Show avatar only on the first message of a same-sender run.
                // A time divider also resets the run because it's a visual break.
                const showAvatar =
                  !prev || prev.sender_type !== msg.sender_type || dividerLabel !== null;

                return (
                  <Fragment key={msg.id}>
                    {dividerLabel && <TimeDivider label={dividerLabel} />}
                    <div
                      data-rail-id={msg.id}
                      data-rail-kind={msg.sender_type === "user" ? "user" : msg.metadata?.error ? "tool-error" : "agent"}
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

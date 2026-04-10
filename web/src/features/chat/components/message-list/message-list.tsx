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
import type { Message, StreamBlock } from "@/types";

/** Distance from the top (px) at which we begin pre-loading older
 *  messages. Generous (~3 viewports) so users rarely see a "loading"
 *  flash — we should already be fetching by the time they get there. */
const PRELOAD_THRESHOLD_PX = 1500;

interface MessageListProps {
  messages: Message[];
  blocks: StreamBlock[];
  isStreaming: boolean;
  isReady: boolean;
  hasMore: boolean;
  loadingEarlier: boolean;
  onLoadEarlier: () => void;
}

/**
 * MessageList — scrollable message container with empty state, streaming
 * response, and paginated history loading.
 *
 * Owns its own scroll container and manages three scroll behaviors:
 *
 *   1. **Initial load** (mount): jump to the bottom so the latest message
 *      is visible without any smooth-scroll animation.
 *   2. **Append** (new incoming message): smooth-scroll to the bottom.
 *      Detected by the LAST message id changing.
 *   3. **Prepend** (Show earlier pagination): preserve the user's view
 *      anchor by adjusting scrollTop by the height diff so the message
 *      they were reading stays fixed on screen. Detected by the FIRST
 *      message id changing while the last stays the same.
 *
 * Pagination uses an *aggressive pre-fetch* strategy rather than waiting
 * for the user to hit the very top:
 *   - A scroll listener pre-loads when within `PRELOAD_THRESHOLD_PX` of
 *     the top, well before the user reaches it.
 *   - After every prepend, an effect re-checks the same threshold and
 *     chains another fetch if we're still close, so multiple small pages
 *     stream in back-to-back without the user ever seeing a loading state.
 *
 * The ref is forwarded to the scroll container so parent hooks (chat
 * export) can read its innerHTML.
 */
export const MessageList = forwardRef<HTMLDivElement, MessageListProps>(
  function MessageList(
    { messages, blocks, isStreaming, isReady, hasMore, loadingEarlier, onLoadEarlier },
    forwardedRef,
  ) {
    const scrollRef = useRef<HTMLDivElement>(null);
    useImperativeHandle(forwardedRef, () => scrollRef.current as HTMLDivElement);

    // Track identity of first/last message + previous scroll height so we
    // can discriminate append vs prepend vs initial mount in one effect.
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

      if (!didInitialScrollRef.current && messages.length > 0) {
        // First time we have messages — jump to bottom (no animation).
        el.scrollTop = el.scrollHeight;
        didInitialScrollRef.current = true;
      } else if (
        prevFirst !== null &&
        firstId !== prevFirst &&
        lastId === prevLast
      ) {
        // Prepend only — adjust scrollTop by the height difference so
        // the viewport anchor stays put.
        const diff = el.scrollHeight - prevScrollHeightRef.current;
        el.scrollTop += diff;
      } else if (prevLast !== null && lastId !== prevLast) {
        // New message appended (or streaming finalized into a saved msg).
        el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      }

      prevFirstIdRef.current = firstId;
      prevLastIdRef.current = lastId;
      prevScrollHeightRef.current = el.scrollHeight;
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
          <div className="mx-auto max-w-container-prose px-6 py-6">
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
                      data-rail-kind={msg.sender_type === "user" ? "user" : "agent"}
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

"use client";

import { useEffect, useRef } from "react";
import { Search, X, ChevronUp, ChevronDown } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { useChatWidth } from "@/features/chat/hooks/use-chat-width";
import type { ChatSearchState } from "@/features/chat/hooks/use-chat-search";
import { cn } from "@/lib/utils";

interface ChatSearchBarProps {
  search: ChatSearchState;
}

/**
 * ChatSearchBar — sticky in-chat search bar.
 *
 * Keys: Enter = next, Shift+Enter = prev, Esc = close.
 */
export function ChatSearchBar({ search }: ChatSearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { widthClass } = useChatWidth();

  useEffect(() => {
    if (!search.open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, [search.open]);

  if (!search.open) return null;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      search.closeSearch();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (e.shiftKey) search.prev();
      else search.next();
    }
  };

  const hasQuery = search.query.trim().length > 0;
  const counterText = !hasQuery
    ? null
    : search.searching
      ? "Searching…"
      : search.matchCount === 0
        ? "0 matches"
        : `${search.currentIdx + 1} of ${search.matchCount}`;
  const showSpinner = search.searching || search.navigating;

  return (
    <div className="shrink-0 border-b border-white/[0.06] bg-canvas/95 backdrop-blur px-6 py-2 animate-fade-in">
      <div className={cn("mx-auto flex items-center gap-2", widthClass)}>
        <Search size={14} strokeWidth={1.75} className="shrink-0 text-fg-muted" />
        <input
          ref={inputRef}
          type="text"
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search in chat…"
          className="flex-1 bg-transparent type-body text-fg-primary placeholder:text-fg-disabled outline-none"
        />

        {counterText && (
          <span
            className={cn(
              "shrink-0 type-caption tabular-nums",
              search.matchCount === 0 && !search.searching
                ? "text-fg-disabled"
                : "text-fg-muted",
            )}
          >
            {counterText}
          </span>
        )}

        {showSpinner && <Spinner size={12} className="text-fg-muted" />}

        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={search.prev}
            disabled={search.matchCount === 0}
            aria-label="Previous match"
            title="Previous match (Shift+Enter)"
            className="flex h-7 w-7 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors disabled:opacity-30 disabled:pointer-events-none"
          >
            <ChevronUp size={14} strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={search.next}
            disabled={search.matchCount === 0}
            aria-label="Next match"
            title="Next match (Enter)"
            className="flex h-7 w-7 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors disabled:opacity-30 disabled:pointer-events-none"
          >
            <ChevronDown size={14} strokeWidth={1.75} />
          </button>
          <button
            type="button"
            onClick={search.closeSearch}
            aria-label="Close search (Esc)"
            title="Close (Esc)"
            className="flex h-7 w-7 items-center justify-center rounded-xs text-fg-muted hover:bg-raised hover:text-fg-primary transition-colors"
          >
            <X size={14} strokeWidth={1.75} />
          </button>
        </div>
      </div>
    </div>
  );
}

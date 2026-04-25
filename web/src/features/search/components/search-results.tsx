"use client";

import Link from "next/link";
import { MessageSquare, AlertCircle } from "@/components/icons";
import { Spinner } from "@/components/ui/spinner";
import { routes } from "@/lib/constants/routes";
import { formatShortDate } from "@/lib/utils/format";
import { cn } from "@/lib/utils";
import type { MessageSearchHit } from "@/features/search/api/search-api";

interface SearchResultsProps {
  hits: MessageSearchHit[];
  loading: boolean;
  error: string | null;
  query: string;
  /** Called when the user clicks a result — typically used by the parent
   *  to clear the search query and dismiss the dropdown. */
  onResultClick: () => void;
}

/**
 * SearchResults — backend message hits group, rendered below the
 * client-side filtered sidebar.
 *
 * Each hit links to its session. The snippet contains the matched
 * substring; we naively highlight it client-side here using a simple
 * substring split.
 */
export function SearchResults({ hits, loading, error, query, onResultClick }: SearchResultsProps) {
  // Show nothing when search is fresh and not yet triggered
  if (!query.trim()) return null;

  return (
    <div className="px-3 pt-2">
      <div className="mb-1.5 flex items-center gap-2 px-3">
        <span className="type-small text-fg-disabled">In messages</span>
        {loading && <Spinner size={10} className="text-fg-disabled" />}
      </div>

      {error && (
        <div className="px-3 py-2 flex items-center gap-2 type-caption text-danger">
          <AlertCircle size={11} strokeWidth={2} />
          <span className="truncate">{error}</span>
        </div>
      )}

      {!loading && !error && hits.length === 0 && query.trim().length >= 2 && (
        <p className="px-3 py-1 type-caption text-fg-disabled">No message matches</p>
      )}

      {hits.length > 0 && (
        <div className="space-y-0.5">
          {hits.map((hit) => (
            <Link
              key={hit.message_id}
              href={routes.session(hit.session_id)}
              onClick={onResultClick}
              className="group block rounded-xs px-3 py-1.5 hover:bg-hover transition-colors"
            >
              <div className="flex items-center gap-1.5 type-caption text-fg-muted">
                <MessageSquare size={10} strokeWidth={2} className="shrink-0" />
                <span className="truncate type-caption-bold text-fg-secondary group-hover:text-fg-primary">
                  {hit.session_title || "Untitled"}
                </span>
                <span className="shrink-0 text-fg-disabled">·</span>
                <span className="shrink-0 text-fg-disabled">{hit.agent_icon || "🤖"}</span>
                <span className="truncate text-fg-disabled">{hit.agent_name}</span>
              </div>
              <p className="mt-0.5 ml-3.5 type-caption text-fg-muted line-clamp-2 leading-snug">
                <SnippetHighlight text={hit.snippet} query={query.trim()} />
              </p>
              <p
                className={cn(
                  "mt-0.5 ml-3.5 type-caption text-fg-disabled",
                  hit.sender_type === "user" && "italic",
                )}
              >
                {hit.sender_type === "user" ? "You" : hit.agent_name} ·{" "}
                {formatShortDate(hit.created_at)}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** Highlight all (case-insensitive) occurrences of `query` in `text`. */
function SnippetHighlight({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let hit = lowerText.indexOf(lowerQuery, cursor);

  while (hit !== -1) {
    if (hit > cursor) parts.push(text.slice(cursor, hit));
    parts.push(
      <mark
        key={`${hit}-${parts.length}`}
        className="bg-warning/30 text-fg-primary rounded-[2px] px-px"
      >
        {text.slice(hit, hit + query.length)}
      </mark>,
    );
    cursor = hit + query.length;
    hit = lowerText.indexOf(lowerQuery, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));

  return <>{parts}</>;
}

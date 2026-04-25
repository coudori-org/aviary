"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Bot,
  GitBranch,
  Loader2,
  MessageSquare,
  Search,
  Workflow as WorkflowIcon,
} from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Kbd } from "@/components/ui/kbd";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { Agent, Workflow } from "@/types";
import type { MessageSearchHit } from "@/features/search/api/search-api";
import { usePaletteResults, type PaletteResults } from "./use-palette-results";

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

type Action =
  | { kind: "agent"; agent: Agent }
  | { kind: "workflow"; workflow: Workflow }
  | { kind: "session"; hit: MessageSearchHit };

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = React.useState("");
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const { loading, results, error } = usePaletteResults(query, open);
  const flat = React.useMemo(() => flatten(results), [results]);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // Defer focus to next tick so the modal is mounted and visible.
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  React.useEffect(() => {
    setActive(0);
  }, [query]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(flat.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        const target = flat[active];
        if (target) {
          e.preventDefault();
          executeAction(target.action, router, onClose);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, flat, active, router]);

  if (!open) return null;

  const trimmed = query.trim();

  return (
    <div
      onClick={onClose}
      className={cn(
        "fixed inset-0 z-[100] flex items-start justify-center pt-[100px]",
        "bg-overlay backdrop-blur-[2px] animate-fade-in-fast",
      )}
      role="presentation"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-[640px] max-w-[calc(100vw-32px)] overflow-hidden",
          "rounded-[12px] border border-border bg-raised shadow-xl",
          "animate-slide-up",
        )}
        role="dialog"
        aria-label="Command palette"
        aria-modal
      >
        <div className="flex items-center gap-[10px] border-b border-border-subtle px-[14px] py-3">
          {loading ? (
            <Loader2 size={16} className="animate-spin text-accent" />
          ) : (
            <Search size={16} className="text-fg-tertiary" />
          )}
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search agents, workflows, sessions…"
            className={cn(
              "flex-1 bg-transparent text-[14px] text-fg-primary outline-none",
              "placeholder:text-fg-muted",
            )}
            aria-label="Search query"
          />
          <Kbd>esc</Kbd>
        </div>

        <div className="max-h-[440px] overflow-y-auto">
          {!trimmed ? (
            <Hint />
          ) : error ? (
            <ErrorHint message={error} />
          ) : flat.length === 0 && !loading ? (
            <EmptyHint />
          ) : (
            <ResultGroups
              results={results}
              query={trimmed}
              active={active}
              onActivate={(i) => setActive(i)}
              onSelect={(action) => executeAction(action, router, onClose)}
              flat={flat}
            />
          )}
        </div>

        <div
          className={cn(
            "flex items-center gap-3 border-t border-border-subtle px-[14px] py-2",
            "text-[11.5px] text-fg-muted",
          )}
        >
          <span className="inline-flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>↵</Kbd> select
          </span>
          <span className="ml-auto">Aviary Search</span>
        </div>
      </div>
    </div>
  );
}

function flatten(r: PaletteResults): Array<{ key: string; action: Action }> {
  const out: Array<{ key: string; action: Action }> = [];
  for (const a of r.agents) out.push({ key: `a:${a.id}`, action: { kind: "agent", agent: a } });
  for (const w of r.workflows) out.push({ key: `w:${w.id}`, action: { kind: "workflow", workflow: w } });
  for (const h of r.sessions)
    out.push({ key: `s:${h.message_id}`, action: { kind: "session", hit: h } });
  return out;
}

function executeAction(
  action: Action,
  router: ReturnType<typeof useRouter>,
  onClose: () => void,
) {
  if (action.kind === "agent") {
    router.push(routes.agentChat(action.agent.id));
  } else if (action.kind === "workflow") {
    router.push(routes.workflowDetail(action.workflow.id));
  } else {
    router.push(routes.agentChat(action.hit.agent_id, action.hit.session_id));
  }
  onClose();
}

interface ResultGroupsProps {
  results: PaletteResults;
  query: string;
  active: number;
  onActivate: (i: number) => void;
  onSelect: (action: Action) => void;
  flat: Array<{ key: string; action: Action }>;
}

function ResultGroups({
  results,
  query,
  active,
  onActivate,
  onSelect,
  flat,
}: ResultGroupsProps) {
  let cursor = 0;
  return (
    <div className="py-1">
      {results.agents.length > 0 && (
        <Section title="Agents" count={results.agents.length}>
          {results.agents.map((a) => {
            const idx = cursor++;
            return (
              <ResultRow
                key={`a:${a.id}`}
                idx={idx}
                active={idx === active}
                onActivate={onActivate}
                onSelect={() => onSelect(flat[idx].action)}
                avatarTone={toneFromId(a.id)}
                avatarIcon={<Bot size={13} />}
                title={a.name}
                subtitle={a.description}
                query={query}
              />
            );
          })}
        </Section>
      )}
      {results.workflows.length > 0 && (
        <Section title="Workflows" count={results.workflows.length}>
          {results.workflows.map((w) => {
            const idx = cursor++;
            return (
              <ResultRow
                key={`w:${w.id}`}
                idx={idx}
                active={idx === active}
                onActivate={onActivate}
                onSelect={() => onSelect(flat[idx].action)}
                avatarTone={toneFromId(w.id)}
                avatarIcon={<WorkflowIcon size={13} />}
                title={w.name}
                subtitle={w.description}
                query={query}
              />
            );
          })}
        </Section>
      )}
      {results.sessions.length > 0 && (
        <Section title="Sessions" count={results.sessions.length}>
          {results.sessions.map((h) => {
            const idx = cursor++;
            return (
              <ResultRow
                key={`s:${h.message_id}`}
                idx={idx}
                active={idx === active}
                onActivate={onActivate}
                onSelect={() => onSelect(flat[idx].action)}
                avatarTone={toneFromId(h.agent_id)}
                avatarIcon={<MessageSquare size={13} />}
                title={h.session_title ?? "(untitled session)"}
                subtitle={h.snippet}
                meta={`${h.agent_name} · ${relativeTime(h.created_at)}`}
                query={query}
                highlightSubtitle
              />
            );
          })}
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <div className="px-1 py-1">
      <div className="flex items-center justify-between px-3 pb-1 pt-2">
        <span className="t-over fg-muted">{title}</span>
        <span className="text-[10.5px] text-fg-muted tabular-nums">{count}</span>
      </div>
      <ul>{children}</ul>
    </div>
  );
}

interface ResultRowProps {
  idx: number;
  active: boolean;
  onActivate: (i: number) => void;
  onSelect: () => void;
  avatarTone: ReturnType<typeof toneFromId>;
  avatarIcon: React.ReactNode;
  title: string;
  subtitle?: string;
  meta?: string;
  query: string;
  highlightSubtitle?: boolean;
}

function ResultRow({
  idx,
  active,
  onActivate,
  onSelect,
  avatarTone,
  avatarIcon,
  title,
  subtitle,
  meta,
  query,
  highlightSubtitle,
}: ResultRowProps) {
  return (
    <li>
      <button
        type="button"
        onMouseEnter={() => onActivate(idx)}
        onMouseDown={(e) => e.preventDefault()}
        onClick={onSelect}
        className={cn(
          "flex w-full items-center gap-3 rounded-[7px] px-3 py-2 text-left",
          "transition-colors duration-fast",
          active ? "bg-accent-soft" : "hover:bg-hover",
        )}
      >
        <Avatar tone={avatarTone} size="md">
          {avatarIcon}
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="t-body font-medium fg-primary truncate">
              {highlight(title, query)}
            </span>
            {meta && (
              <span className="ml-auto truncate text-[11px] text-fg-tertiary">
                {meta}
              </span>
            )}
          </div>
          {subtitle && (
            <div className="mt-0.5 truncate text-[11.5px] text-fg-tertiary">
              {highlightSubtitle ? highlight(subtitle, query) : subtitle}
            </div>
          )}
        </div>
      </button>
    </li>
  );
}

function highlight(text: string, query: string): React.ReactNode {
  if (!query) return text;
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const idx = lower.indexOf(q);
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded-[3px] bg-accent-soft px-[1px] text-fg-primary">
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const min = Math.floor(ms / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.floor(d / 30);
  return mo < 12 ? `${mo}mo ago` : `${Math.floor(mo / 12)}y ago`;
}

function Hint() {
  return (
    <div className="px-7 py-10 text-center text-[12.5px] text-fg-muted">
      <Search size={20} className="mx-auto mb-2 text-fg-muted" />
      Search across agents, workflows, and full-text session messages.
      <div className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-fg-muted">
        Try{" "}
        <code className="rounded-[4px] bg-sunk px-1 py-px t-mono">PR review</code>
        ,{" "}
        <code className="rounded-[4px] bg-sunk px-1 py-px t-mono">deploy</code>
      </div>
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="px-7 py-10 text-center text-[12.5px] text-fg-muted">
      No matches.
    </div>
  );
}

function ErrorHint({ message }: { message: string }) {
  return (
    <div className="px-7 py-10 text-center text-[12.5px] text-status-error">
      {message}
    </div>
  );
}

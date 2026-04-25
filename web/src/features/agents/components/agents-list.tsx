"use client";

import * as React from "react";
import Link from "next/link";
import {
  Plus,
  Upload,
  Search as SearchIcon,
  LayoutGrid,
  Layers,
  Bot,
  Lock,
  Globe,
  Download,
} from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AssetKind } from "@/components/ui/kind-badge";
import { cn } from "@/lib/utils";
import { routes } from "@/lib/constants/routes";
import { useAgentsData } from "../hooks/use-agents-data";
import { AgentCard } from "./agent-card";
import { AgentListRow, AGENT_LIST_COLS } from "./agent-list-row";

type Filter = "all" | AssetKind;
type View = "grid" | "list";

export function AgentsList() {
  const { agents, meta, loading, error } = useAgentsData();
  const [filter, setFilter] = React.useState<Filter>("all");
  const [query, setQuery] = React.useState("");
  const [view, setView] = React.useState<View>("grid");

  // Backend has no published/imported yet — every owned agent is "private".
  // Marketplace (Stage C1) will start tagging real kinds.
  const kindFor = (): AssetKind => "private";

  const counts: Record<Filter, number> = {
    all: agents.length,
    private: agents.length,
    published: 0,
    imported: 0,
  };

  const q = query.trim().toLowerCase();
  const visible = agents.filter((a) => {
    if (filter !== "all" && kindFor() !== filter) return false;
    if (!q) return true;
    return (
      a.name.toLowerCase().includes(q) ||
      a.slug.toLowerCase().includes(q) ||
      (a.description ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-8 pt-5">
        <header className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h1 className="t-hero fg-primary">Agents</h1>
            <p className="mt-[2px] t-small fg-tertiary">
              Manage agents you built and ones imported from Marketplace.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href={routes.marketplace}>
                <Upload size={13} /> Import
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href={routes.agentNew}>
                <Plus size={13} /> New Agent
              </Link>
            </Button>
          </div>
        </header>

        <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle pb-3">
          <FilterTabs filter={filter} counts={counts} onChange={setFilter} />
          <div className="flex-1" />
          <div className="relative">
            <SearchIcon
              size={14}
              className="pointer-events-none absolute left-[10px] top-1/2 -translate-y-1/2 text-fg-muted"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter agents…"
              className="w-[220px] pl-8"
            />
          </div>
          <ViewToggle view={view} onChange={setView} />
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-8 py-5 pb-12">
        {error && <ErrorBanner message={error} />}
        {loading && agents.length === 0 ? (
          view === "grid" ? (
            <GridSkeleton count={6} />
          ) : (
            <ListSkeleton count={6} />
          )
        ) : visible.length === 0 ? (
          <EmptyState
            filter={filter}
            searchActive={q.length > 0}
            totalAgents={agents.length}
          />
        ) : view === "grid" ? (
          <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(288px,1fr))]">
            {visible.map((a) => (
              <AgentCard
                key={a.id}
                agent={a}
                sessionCount={meta[a.id]?.sessionCount}
                toolCount={meta[a.id]?.toolCount}
                kind={kindFor()}
              />
            ))}
          </div>
        ) : (
          <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
            <div
              className={cn(
                AGENT_LIST_COLS,
                "border-b border-border-subtle px-4 py-[10px]",
                "t-over fg-muted"
              )}
            >
              <span>Agent</span>
              <span>Description</span>
              <span>Kind</span>
              <span>Tools</span>
              <span>Sessions</span>
              <span>Updated</span>
              <span />
            </div>
            {visible.map((a, i) => (
              <AgentListRow
                key={a.id}
                agent={a}
                sessionCount={meta[a.id]?.sessionCount}
                toolCount={meta[a.id]?.toolCount}
                kind={kindFor()}
                divider={i < visible.length - 1}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FilterTabs({
  filter,
  counts,
  onChange,
}: {
  filter: Filter;
  counts: Record<Filter, number>;
  onChange: (f: Filter) => void;
}) {
  const tabs: Array<{ id: Filter; label: string; Icon?: typeof Lock }> = [
    { id: "all", label: "All" },
    { id: "private", label: "Private", Icon: Lock },
    { id: "published", label: "Published", Icon: Globe },
    { id: "imported", label: "Imported", Icon: Download },
  ];
  return (
    <div className="flex gap-[2px] rounded-[8px] bg-sunk p-[2px]">
      {tabs.map((t) => {
        const active = filter === t.id;
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={cn(
              "inline-flex items-center gap-[6px] rounded-[6px] px-3 py-[6px]",
              "text-[12.5px] font-medium transition-colors duration-fast",
              active
                ? "bg-raised text-fg-primary shadow-sm"
                : "text-fg-tertiary hover:text-fg-secondary"
            )}
          >
            {t.Icon && <t.Icon size={12} />}
            {t.label}
            <span className="num text-[11px] text-fg-muted">{counts[t.id]}</span>
          </button>
        );
      })}
    </div>
  );
}

function ViewToggle({
  view,
  onChange,
}: {
  view: View;
  onChange: (v: View) => void;
}) {
  const options: Array<{ id: View; Icon: typeof LayoutGrid; label: string }> = [
    { id: "grid", Icon: LayoutGrid, label: "Grid view" },
    { id: "list", Icon: Layers, label: "List view" },
  ];
  return (
    <div className="flex rounded-[6px] bg-sunk p-[1px]">
      {options.map(({ id, Icon, label }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          aria-label={label}
          className={cn(
            "grid h-6 w-6 place-items-center rounded-[5px] transition-colors duration-fast",
            view === id ? "bg-raised text-fg-primary" : "text-fg-muted hover:text-fg-secondary"
          )}
        >
          <Icon size={13} />
        </button>
      ))}
    </div>
  );
}

function EmptyState({
  filter,
  searchActive,
  totalAgents,
}: {
  filter: Filter;
  searchActive: boolean;
  totalAgents: number;
}) {
  if (searchActive) {
    return (
      <Centered icon={<SearchIcon size={20} />}>
        <h2 className="t-h3 fg-primary">No agents match your search</h2>
        <p className="mt-1 text-[12.5px] text-fg-muted">Try a different keyword.</p>
      </Centered>
    );
  }
  if (filter === "published") {
    return (
      <Centered icon={<Globe size={20} />}>
        <h2 className="t-h3 fg-primary">Nothing published yet</h2>
        <p className="mt-1 max-w-[360px] text-[12.5px] text-fg-muted">
          Publish an agent to share it with the team via Marketplace once it
          ships.
        </p>
      </Centered>
    );
  }
  if (filter === "imported") {
    return (
      <Centered icon={<Download size={20} />}>
        <h2 className="t-h3 fg-primary">No imports yet</h2>
        <p className="mt-1 max-w-[360px] text-[12.5px] text-fg-muted">
          Imported agents will appear here once Marketplace is available.
        </p>
      </Centered>
    );
  }
  if (totalAgents === 0) {
    return (
      <Centered icon={<Bot size={20} />}>
        <h2 className="t-h3 fg-primary">No agents yet</h2>
        <p className="mt-1 max-w-[360px] text-[12.5px] text-fg-muted">
          Create your first agent to get started.
        </p>
        <Button asChild className="mt-3" size="sm">
          <Link href={routes.agentNew}>
            <Plus size={13} /> New Agent
          </Link>
        </Button>
      </Centered>
    );
  }
  return null;
}

function Centered({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[10px] border border-border-subtle bg-raised px-6 py-16 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-[8px] bg-hover text-fg-tertiary">
        {icon}
      </div>
      <div>{children}</div>
    </div>
  );
}

function GridSkeleton({ count }: { count: number }) {
  return (
    <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(288px,1fr))]">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-[148px] animate-shimmer rounded-[10px] border border-border-subtle"
        />
      ))}
    </div>
  );
}

function ListSkeleton({ count }: { count: number }) {
  return (
    <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            AGENT_LIST_COLS,
            "px-4 py-[10px]",
            i < count - 1 && "border-b border-border-subtle"
          )}
        >
          <div className="h-5 animate-shimmer rounded-[4px]" />
          <div className="h-3 animate-shimmer rounded-[4px]" />
          <div className="h-5 w-20 animate-shimmer rounded-[4px]" />
          <div className="h-3 w-10 animate-shimmer rounded-[4px]" />
          <div className="h-3 w-10 animate-shimmer rounded-[4px]" />
          <div className="h-3 w-16 animate-shimmer rounded-[4px]" />
          <div />
        </div>
      ))}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 rounded-[10px] border border-status-error bg-status-error-soft px-4 py-3 text-[12.5px] text-status-error">
      Failed to load agents: {message}
    </div>
  );
}

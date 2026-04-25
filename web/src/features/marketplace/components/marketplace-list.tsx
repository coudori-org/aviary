"use client";

import * as React from "react";
import {
  ArrowUpDown,
  Bot,
  GitBranch,
  Layers,
  LayoutGrid,
  Search as SearchIcon,
  Store,
  Upload,
} from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingState } from "@/components/feedback/loading-state";
import {
  marketplaceApi,
  MARKETPLACE_CATEGORIES,
} from "@/features/marketplace/api/marketplace-api";
import { cn } from "@/lib/utils";
import type {
  MarketplaceItemSummary,
  MarketplaceKind,
} from "@/types/marketplace";
import { MarketplaceCard } from "./marketplace-card";
import { MarketplaceRow, MARKETPLACE_ROW_COLS } from "./marketplace-row";

type View = "grid" | "list";
type Sort = "popular" | "rating" | "new" | "updated";

const SORTS: Array<{ id: Sort; label: string }> = [
  { id: "popular", label: "Popular" },
  { id: "rating", label: "Highest rated" },
  { id: "new", label: "Newest" },
  { id: "updated", label: "Recently updated" },
];

const KIND_TABS: Array<{
  id: MarketplaceKind | "all";
  label: string;
  Icon: typeof Bot;
}> = [
  { id: "all", label: "All", Icon: Store },
  { id: "agent", label: "Agents", Icon: Bot },
  { id: "workflow", label: "Workflows", Icon: GitBranch },
];

export function MarketplaceList() {
  const [kind, setKind] = React.useState<MarketplaceKind | "all">("all");
  const [category, setCategory] = React.useState<string>("All");
  const [query, setQuery] = React.useState("");
  const [mineOnly, setMineOnly] = React.useState(false);
  const [sort, setSort] = React.useState<Sort>("popular");
  const [view, setView] = React.useState<View>("grid");
  const [items, setItems] = React.useState<MarketplaceItemSummary[]>([]);
  const [featured, setFeatured] = React.useState<MarketplaceItemSummary[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    marketplaceApi
      .list({
        kind: kind === "all" ? undefined : kind,
        category,
        query,
        mineOnly,
        sort,
      })
      .then((r) => {
        if (active) setItems(r);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [kind, category, query, mineOnly, sort]);

  React.useEffect(() => {
    marketplaceApi.featured().then(setFeatured);
  }, []);

  const showFeatured =
    !loading && !mineOnly && category === "All" && !query.trim() && featured.length > 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1400px] px-8 pt-5">
        <header className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h1 className="t-hero fg-primary">Marketplace</h1>
            <p className="mt-[2px] t-small fg-tertiary">
              Discover agents and workflows shared across the company.
            </p>
          </div>
          <Button variant="outline" size="sm" disabled title="Coming soon">
            <Upload size={13} /> Publish from my library
          </Button>
        </header>

        <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle pb-3">
          <KindTabs kind={kind} onChange={setKind} />
          <button
            type="button"
            onClick={() => setMineOnly((v) => !v)}
            className={cn(
              "inline-flex items-center gap-[6px] rounded-[6px] px-3 py-[6px]",
              "text-[12.5px] font-medium transition-colors duration-fast",
              mineOnly
                ? "bg-accent-soft text-accent border border-accent/30"
                : "border border-transparent text-fg-tertiary hover:text-fg-secondary",
            )}
          >
            <Upload size={12} /> Published by me
          </button>
          <div className="flex-1" />
          <div className="relative">
            <SearchIcon
              size={14}
              className="pointer-events-none absolute left-[10px] top-1/2 -translate-y-1/2 text-fg-muted"
            />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search marketplace…"
              className="w-[260px] pl-8"
            />
          </div>
          <SortMenu sort={sort} onChange={setSort} />
          <ViewToggle view={view} onChange={setView} />
        </div>
      </div>

      <div className="mx-auto flex max-w-[1400px] gap-6 px-8 py-5 pb-12">
        <CategoryRail
          active={category}
          onChange={setCategory}
          disabled={kind === "workflow"}
        />

        <div className="min-w-0 flex-1">
          {loading && items.length === 0 ? (
            <LoadingState label="Loading marketplace…" />
          ) : items.length === 0 ? (
            <EmptyState query={query} mineOnly={mineOnly} />
          ) : (
            <>
              {showFeatured && (
                <section className="mb-6">
                  <h2 className="t-over fg-muted mb-2">Featured</h2>
                  <div className="grid grid-cols-3 gap-3">
                    {featured.slice(0, 3).map((m) => (
                      <MarketplaceCard key={m.id} item={m} featured />
                    ))}
                  </div>
                </section>
              )}

              <section>
                <h2 className="t-over fg-muted mb-2">
                  {mineOnly
                    ? "Published by me"
                    : kind === "workflow"
                    ? "All workflows"
                    : kind === "agent"
                    ? category === "All"
                      ? "All agents"
                      : category
                    : category === "All"
                    ? "All items"
                    : category}
                  <span className="ml-2 text-fg-tertiary tabular-nums">
                    {items.length}
                  </span>
                </h2>
                {view === "grid" ? (
                  <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(288px,1fr))]">
                    {items.map((m) => (
                      <MarketplaceCard key={m.id} item={m} />
                    ))}
                  </div>
                ) : (
                  <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
                    <div
                      className={cn(
                        MARKETPLACE_ROW_COLS,
                        "border-b border-border-subtle px-4 py-[10px] t-over fg-muted",
                      )}
                    >
                      <span />
                      <span>Item</span>
                      <span>Stats</span>
                      <span>Category</span>
                      <span />
                    </div>
                    {items.map((m, i) => (
                      <MarketplaceRow
                        key={m.id}
                        item={m}
                        divider={i < items.length - 1}
                      />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function KindTabs({
  kind,
  onChange,
}: {
  kind: MarketplaceKind | "all";
  onChange: (k: MarketplaceKind | "all") => void;
}) {
  return (
    <div className="flex gap-[2px] rounded-[8px] bg-sunk p-[2px]">
      {KIND_TABS.map((t) => {
        const active = kind === t.id;
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
                : "text-fg-tertiary hover:text-fg-secondary",
            )}
          >
            <t.Icon size={12} />
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

function CategoryRail({
  active,
  onChange,
  disabled,
}: {
  active: string;
  onChange: (c: string) => void;
  disabled?: boolean;
}) {
  return (
    <aside className="hidden w-[180px] shrink-0 lg:block">
      <h2 className="t-over fg-muted px-2 pb-2 pt-1">Categories</h2>
      <ul className="flex flex-col gap-px">
        {MARKETPLACE_CATEGORIES.map((c) => (
          <li key={c}>
            <button
              type="button"
              onClick={() => onChange(c)}
              disabled={disabled && c !== "All"}
              className={cn(
                "w-full rounded-[6px] px-2 py-[6px] text-left text-[12.5px]",
                "transition-colors duration-fast",
                active === c
                  ? "bg-hover font-medium text-fg-primary"
                  : "text-fg-secondary hover:bg-hover/60 hover:text-fg-primary",
                disabled && c !== "All" && "opacity-40 cursor-not-allowed hover:bg-transparent",
              )}
            >
              {c}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function SortMenu({
  sort,
  onChange,
}: {
  sort: Sort;
  onChange: (s: Sort) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);
  const current = SORTS.find((s) => s.id === sort) ?? SORTS[0];
  return (
    <div ref={ref} className="relative">
      <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
        <ArrowUpDown size={13} />
        {current.label}
      </Button>
      {open && (
        <div
          className={cn(
            "absolute right-0 top-[calc(100%+4px)] z-20 w-44 overflow-hidden rounded-[8px]",
            "border border-border-subtle bg-raised shadow-lg",
          )}
        >
          {SORTS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => {
                onChange(s.id);
                setOpen(false);
              }}
              className={cn(
                "block w-full px-3 py-2 text-left text-[12.5px]",
                "transition-colors duration-fast hover:bg-hover",
                s.id === sort ? "text-fg-primary" : "text-fg-secondary",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
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
  return (
    <div className="flex rounded-[6px] bg-sunk p-[1px]">
      {(
        [
          { id: "grid" as const, Icon: LayoutGrid, label: "Grid view" },
          { id: "list" as const, Icon: Layers, label: "List view" },
        ]
      ).map(({ id, Icon, label }) => (
        <button
          key={id}
          type="button"
          aria-label={label}
          onClick={() => onChange(id)}
          className={cn(
            "grid h-6 w-6 place-items-center rounded-[5px] transition-colors duration-fast",
            view === id ? "bg-raised text-fg-primary" : "text-fg-muted hover:text-fg-secondary",
          )}
        >
          <Icon size={13} />
        </button>
      ))}
    </div>
  );
}

function EmptyState({ query, mineOnly }: { query: string; mineOnly: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[10px] border border-border-subtle bg-raised px-6 py-16 text-center">
      <div className="grid h-10 w-10 place-items-center rounded-[8px] bg-hover text-fg-tertiary">
        <Store size={20} />
      </div>
      <h2 className="t-h3 fg-primary">
        {query ? "No matches" : mineOnly ? "Nothing published yet" : "No items"}
      </h2>
      <p className="max-w-[360px] text-[12.5px] text-fg-muted">
        {query
          ? "Try a different keyword or clear the search."
          : mineOnly
          ? "Publish an agent or workflow from your library to share it here."
          : "Try a different category or kind."}
      </p>
    </div>
  );
}

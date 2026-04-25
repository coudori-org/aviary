"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bot,
  Check,
  ChevronLeft,
  Download,
  Play,
  Star,
  Workflow as WorkflowIcon,
} from "@/components/icons";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { marketplaceApi } from "@/features/marketplace/api/marketplace-api";
import { usePageCrumb } from "@/features/layout/providers/page-header-provider";
import { routes } from "@/lib/constants/routes";
import { toneFromId } from "@/lib/tone";
import { cn } from "@/lib/utils";
import type { MarketplaceItem } from "@/types/marketplace";

const N = new Intl.NumberFormat("en-US");

interface Props {
  itemId: string;
}

export function MarketplaceDetail({ itemId }: Props) {
  const router = useRouter();
  const [item, setItem] = React.useState<MarketplaceItem | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [toast, setToast] = React.useState<string | null>(null);

  React.useEffect(() => {
    marketplaceApi
      .get(itemId)
      .then((r) => {
        if (!r) {
          setError("Item not found");
          return;
        }
        setItem(r);
      })
      .catch((e: Error) => setError(e.message));
  }, [itemId]);

  const crumb = React.useMemo(
    () =>
      item ? (
        <span className="inline-flex items-center gap-1.5">
          <Link
            href={routes.marketplace}
            className="text-fg-tertiary transition-colors hover:text-fg-primary"
          >
            Marketplace
          </Link>
          <span className="text-fg-muted">/</span>
          <span className="text-fg-primary">{item.name}</span>
        </span>
      ) : null,
    [item],
  );
  usePageCrumb(crumb);

  const handleImport = React.useCallback(() => {
    if (!item || item.imported) return;
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      setItem((prev) => (prev ? { ...prev, imported: true } : prev));
      setToast(
        item.kind === "workflow"
          ? "Workflow imported. Find it under Workflows."
          : "Agent imported. Find it under Agents.",
      );
    }, 500);
  }, [item]);

  React.useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  if (error) return <ErrorState description={error} />;
  if (!item) return <LoadingState fullHeight label="Loading item…" />;

  const tone = toneFromId(item.id);
  const Icon = item.kind === "workflow" ? WorkflowIcon : Bot;

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-[1100px] px-8 py-6">
        <button
          type="button"
          onClick={() => router.back()}
          className="mb-4 inline-flex items-center gap-1 text-[12.5px] text-fg-tertiary transition-colors hover:text-fg-primary"
        >
          <ChevronLeft size={13} /> Marketplace
        </button>

        <header
          className={cn(
            "rounded-[10px] border border-border-subtle bg-raised p-6",
            "flex gap-6",
          )}
        >
          <Avatar tone={tone} size="xl">
            <Icon size={24} />
          </Avatar>
          <div className="min-w-0 flex-1">
            <h1 className="t-h1 fg-primary">{item.name}</h1>
            <div className="mt-1.5 flex items-center gap-2 text-[12.5px] text-fg-tertiary">
              <span>by {item.author.display_name}</span>
              <span>·</span>
              <span className="t-mono">{item.version}</span>
              <span>·</span>
              <Badge variant="default" className="h-[19px] text-[10.5px]">
                {item.category}
              </Badge>
              {item.mine && (
                <Badge variant="accent" className="h-[19px] text-[10.5px]">
                  Yours
                </Badge>
              )}
            </div>
            <p className="mt-3 text-[13px] text-fg-secondary leading-relaxed">
              {item.description}
            </p>
            <div className="mt-4 flex items-center gap-2">
              {item.imported ? (
                <Button variant="outline" size="sm" disabled>
                  <Check size={13} /> Imported
                </Button>
              ) : (
                <Button onClick={handleImport} disabled={busy} size="sm">
                  <Download size={13} />
                  {busy ? "Importing…" : `Import ${item.kind}`}
                </Button>
              )}
              <Button variant="outline" size="sm" disabled title="Coming soon">
                <Play size={13} /> Try in sandbox
              </Button>
              <Button variant="ghost" size="sm" disabled title="Coming soon">
                <Star size={13} /> Star
              </Button>
            </div>
          </div>
          <div className="hidden shrink-0 flex-col gap-4 border-l border-border-subtle pl-6 sm:flex">
            <Stat label="Installs" value={N.format(item.installs)} />
            <Stat
              label="Rating"
              value={
                <span className="inline-flex items-center gap-1">
                  <span className="t-mono">{item.rating.toFixed(1)}</span>
                  <Star size={12} className="text-status-warn" />
                </span>
              }
            />
            <Stat label="Updated" value={relativeDays(item.updated_at)} />
            <Stat label="License" value={item.license} />
          </div>
        </header>

        <div className="mt-4 grid gap-4 [grid-template-columns:2fr_1fr]">
          <section className="rounded-[10px] border border-border-subtle bg-raised p-5">
            <h2 className="t-h3 fg-primary">Overview</h2>
            <p className="mt-2 text-[13px] text-fg-secondary leading-relaxed">
              {item.long_description}
            </p>

            <h2 className="t-h3 fg-primary mt-5">Required tools</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.required_tools.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center rounded-[5px] border border-border-subtle bg-sunk px-2 py-[3px] text-[11px] t-mono text-fg-secondary"
                >
                  {t}
                </span>
              ))}
            </div>

            <h2 className="t-h3 fg-primary mt-5">Changelog</h2>
            <ol className="mt-2 flex flex-col divide-y divide-border-subtle">
              {item.changelog.map((c) => (
                <li key={c.version} className="py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="t-mono text-[12px] text-fg-primary">
                      {c.version}
                    </span>
                    <span className="text-[11.5px] text-fg-tertiary">
                      {relativeDays(c.date)}
                    </span>
                  </div>
                  <ul className="mt-1 list-inside list-disc text-[12.5px] text-fg-secondary marker:text-fg-muted">
                    {c.notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </section>

          <aside className="space-y-4">
            <div className="rounded-[10px] border border-border-subtle bg-raised p-4">
              <h3 className="t-over fg-muted">Author</h3>
              <div className="mt-2 flex items-center gap-2">
                <Avatar tone={toneFromId(item.author.handle)} size="md">
                  {item.author.display_name.slice(0, 1)}
                </Avatar>
                <div className="min-w-0">
                  <div className="t-body fg-primary truncate">
                    {item.author.display_name}
                  </div>
                  <div className="t-mono text-[11px] text-fg-tertiary truncate">
                    {item.author.handle}
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-[10px] border border-border-subtle bg-raised p-4">
              <h3 className="t-over fg-muted">Stats</h3>
              <div className="mt-2 grid grid-cols-2 gap-3 sm:hidden">
                <Stat label="Installs" value={N.format(item.installs)} />
                <Stat label="Rating" value={`${item.rating.toFixed(1)} ★`} />
                <Stat label="Updated" value={relativeDays(item.updated_at)} />
                <Stat label="License" value={item.license} />
              </div>
              <ul className="mt-2 hidden flex-col gap-2 text-[12px] text-fg-secondary sm:flex">
                <li className="flex items-center justify-between">
                  <span className="text-fg-tertiary">Kind</span>
                  <span className="capitalize">{item.kind}</span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="text-fg-tertiary">Category</span>
                  <span>{item.category}</span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="text-fg-tertiary">Latest</span>
                  <span className="t-mono">{item.version}</span>
                </li>
                <li className="flex items-center justify-between">
                  <span className="text-fg-tertiary">License</span>
                  <span>{item.license}</span>
                </li>
              </ul>
            </div>
          </aside>
        </div>
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-[8px] border border-border-subtle bg-raised px-3 py-2 text-[12.5px] text-fg-primary shadow-lg">
          <Check size={13} className="text-status-live" />
          {toast}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <div className="t-over fg-muted">{label}</div>
      <div className="mt-1 t-h3 fg-primary tabular-nums">{value}</div>
    </div>
  );
}

function relativeDays(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const d = Math.floor(ms / 86_400_000);
  if (d <= 0) return "today";
  if (d === 1) return "1d ago";
  if (d < 30) return `${d}d ago`;
  const m = Math.floor(d / 30);
  if (m === 1) return "1mo ago";
  if (m < 12) return `${m}mo ago`;
  const y = Math.floor(d / 365);
  return y === 1 ? "1y ago" : `${y}y ago`;
}

"use client";

import * as React from "react";
import { Check, Key, Plus, RefreshCw, X } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/feedback/loading-state";
import {
  credentialsApi,
  type CredentialKey,
} from "@/features/settings/api/credentials-api";

export function CredentialsPanel() {
  const [items, setItems] = React.useState<CredentialKey[] | null>(null);
  React.useEffect(() => {
    credentialsApi.list().then(setItems);
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-[10px] border border-border-subtle bg-raised p-5">
        <div className="flex items-start gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-[7px] bg-accent-soft text-accent">
            <Key size={15} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="t-h2 fg-primary">Vault credentials</h2>
            <p className="mt-1 text-[12.5px] text-fg-secondary leading-relaxed">
              Aviary stores per-user secrets at{" "}
              <code className="t-mono text-[11.5px] text-fg-primary">
                secret/aviary/credentials/&lcub;sub&rcub;/&lcub;key&rcub;
              </code>
              . The supervisor and LiteLLM read them at request time;
              they are never sent to your browser.
            </p>
          </div>
        </div>
      </div>

      {items === null ? (
        <LoadingState label="Loading credentials…" />
      ) : (
        <div className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
          <header className="grid grid-cols-[1fr_120px_140px_120px] gap-4 border-b border-border-subtle px-5 py-[10px] t-over fg-muted">
            <span>Key</span>
            <span>Status</span>
            <span>Scope</span>
            <span />
          </header>
          <ul>
            {items.map((c, i) => (
              <li
                key={c.id}
                className={
                  i < items.length - 1 ? "border-b border-border-subtle" : ""
                }
              >
                <CredentialRow item={c} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[11.5px] text-fg-muted">
        Editing keys from the web UI is coming soon. Until then, set them via
        Vault directly: <code className="t-mono text-[11px]">vault kv put secret/aviary/credentials/&lcub;sub&rcub;/&lcub;key&rcub; value=…</code>
      </p>
    </div>
  );
}

function CredentialRow({ item }: { item: CredentialKey }) {
  const connected = item.status === "connected";
  return (
    <div className="grid grid-cols-[1fr_120px_140px_120px] items-center gap-4 px-5 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="t-body font-medium fg-primary">{item.label}</span>
          <code className="t-mono text-[11px] text-fg-tertiary">{item.id}</code>
        </div>
        <p className="mt-0.5 text-[12px] text-fg-tertiary">{item.description}</p>
        {item.last_rotated && connected && (
          <p className="mt-0.5 text-[11px] text-fg-muted">
            Rotated {relativeDays(item.last_rotated)}
          </p>
        )}
      </div>
      <div>
        {connected ? (
          <Badge variant="success" className="h-[22px]">
            <Check size={11} strokeWidth={2.4} /> Connected
          </Badge>
        ) : (
          <Badge variant="default" className="h-[22px] text-fg-tertiary">
            <X size={11} strokeWidth={2.4} /> Not set
          </Badge>
        )}
      </div>
      <span className="text-[12px] text-fg-tertiary">{item.scope}</span>
      <div className="flex justify-end gap-1">
        {connected ? (
          <Button variant="ghost" size="sm" disabled title="Coming soon">
            <RefreshCw size={12} /> Rotate
          </Button>
        ) : (
          <Button variant="outline" size="sm" disabled title="Coming soon">
            <Plus size={12} /> Add
          </Button>
        )}
      </div>
    </div>
  );
}

function relativeDays(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const d = Math.max(0, Math.floor(ms / 86_400_000));
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  if (d < 30) return `${d}d ago`;
  const m = Math.floor(d / 30);
  if (m === 1) return "1mo ago";
  if (m < 12) return `${m}mo ago`;
  const y = Math.floor(d / 365);
  return y === 1 ? "1y ago" : `${y}y ago`;
}

"use client";

import * as React from "react";
import { Check, Key, Lock, Save, Trash2, X } from "@/components/icons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingState } from "@/components/feedback/loading-state";
import {
  credentialsApi,
  type CredentialKeyStatus,
  type CredentialNamespace,
  type CredentialsResponse,
} from "@/features/settings/api/credentials-api";
import { extractErrorMessage } from "@/lib/http";

export function CredentialsPanel() {
  const [data, setData] = React.useState<CredentialsResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    try {
      setData(await credentialsApi.list());
      setError(null);
    } catch (e) {
      setError(extractErrorMessage(e));
    }
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="flex flex-col gap-4">
      <Header />

      {!data?.vault_enabled && data && <VaultDisabledNotice />}

      {error && (
        <div className="rounded-[10px] border border-status-error/40 bg-status-error-soft p-4 text-[12.5px] text-status-error">
          {error}
        </div>
      )}

      {data === null ? (
        <LoadingState label="Loading credentials…" />
      ) : (
        <div className="flex flex-col gap-4">
          {data.namespaces.map((ns) => (
            <NamespaceCard
              key={ns.namespace}
              ns={ns}
              vaultEnabled={data.vault_enabled}
              onChanged={refresh}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Header() {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-5">
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-[7px] bg-accent-soft text-accent">
          <Key size={15} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="t-h2 fg-primary">Credentials</h2>
          <p className="mt-1 text-[12.5px] text-fg-secondary leading-relaxed">
            Provide the API keys and tokens your agents need to reach
            external services — your LLM provider, GitHub, and any
            connected tools (Jira, Confluence, …). Fill in each field and
            save; agents will pick up the new value on their next call.
            Missing credentials cause the matching tool to fail.
          </p>
        </div>
      </div>
    </div>
  );
}

function VaultDisabledNotice() {
  return (
    <div className="flex items-start gap-3 rounded-[10px] border border-border-subtle bg-status-warn-soft p-4 text-[12.5px] text-status-warn">
      <Lock size={14} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">Vault is not configured.</p>
        <p className="mt-0.5 text-fg-secondary leading-relaxed">
          Credentials are loaded from <code className="t-mono text-[11px]">config.yaml</code>{" "}
          (the <code className="t-mono text-[11px]">secrets:</code> table) and
          can&apos;t be edited from the UI. Set <code className="t-mono text-[11px]">VAULT_ADDR</code>{" "}
          and <code className="t-mono text-[11px]">VAULT_TOKEN</code> in the
          project root <code className="t-mono text-[11px]">.env</code> to
          switch to Vault-backed editing.
        </p>
      </div>
    </div>
  );
}

interface NamespaceCardProps {
  ns: CredentialNamespace;
  vaultEnabled: boolean;
  onChanged: () => Promise<void> | void;
}

function NamespaceCard({ ns, vaultEnabled, onChanged }: NamespaceCardProps) {
  return (
    <section className="overflow-hidden rounded-[10px] border border-border-subtle bg-raised">
      <header className="flex items-baseline justify-between border-b border-border-subtle px-5 py-3">
        <div className="min-w-0">
          <h3 className="t-h3 fg-primary">{ns.label}</h3>
          {ns.description && (
            <p className="mt-0.5 text-[12px] text-fg-tertiary">
              {ns.description}
            </p>
          )}
        </div>
        <code className="t-mono text-[11px] text-fg-muted shrink-0">
          {ns.namespace}
        </code>
      </header>
      <ul>
        {ns.keys.map((k, i) => (
          <li
            key={k.key}
            className={
              i < ns.keys.length - 1 ? "border-b border-border-subtle" : ""
            }
          >
            <CredentialRow
              namespace={ns.namespace}
              item={k}
              vaultEnabled={vaultEnabled}
              onChanged={onChanged}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface CredentialRowProps {
  namespace: string;
  item: CredentialKeyStatus;
  vaultEnabled: boolean;
  onChanged: () => Promise<void> | void;
}

function CredentialRow({ namespace, item, vaultEnabled, onChanged }: CredentialRowProps) {
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState<"save" | "delete" | null>(null);
  const [rowError, setRowError] = React.useState<string | null>(null);

  const editable = vaultEnabled && busy === null;
  const placeholder = item.configured
    ? "Replace value (current value hidden)"
    : `Enter ${item.label.toLowerCase()}`;

  const onSave = async () => {
    if (!draft.trim()) return;
    setBusy("save");
    setRowError(null);
    try {
      await credentialsApi.write(namespace, item.key, draft);
      setDraft("");
      await onChanged();
    } catch (e) {
      setRowError(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const onDelete = async () => {
    setBusy("delete");
    setRowError(null);
    try {
      await credentialsApi.remove(namespace, item.key);
      await onChanged();
    } catch (e) {
      setRowError(extractErrorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="grid grid-cols-[200px_120px_1fr_auto] items-center gap-3 px-5 py-3">
      <div className="min-w-0">
        <div className="t-body fg-primary truncate">{item.label}</div>
        <code className="t-mono text-[11px] text-fg-tertiary truncate block">
          {item.key}
        </code>
      </div>
      <div>
        {item.configured ? (
          <Badge variant="success" className="h-[22px]">
            <Check size={11} strokeWidth={2.4} /> Set
          </Badge>
        ) : (
          <Badge variant="default" className="h-[22px] text-fg-tertiary">
            <X size={11} strokeWidth={2.4} /> Not set
          </Badge>
        )}
      </div>
      <div className="min-w-0">
        <Input
          type="password"
          autoComplete="new-password"
          spellCheck={false}
          placeholder={vaultEnabled ? placeholder : "Read-only (Vault disabled)"}
          value={draft}
          disabled={!editable}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSave();
          }}
        />
        {rowError && (
          <p className="mt-1 text-[11.5px] text-status-error">{rowError}</p>
        )}
      </div>
      <div className="flex justify-end gap-1">
        <Button
          variant="default"
          size="sm"
          disabled={!editable || draft.trim().length === 0}
          onClick={onSave}
        >
          <Save size={12} /> {busy === "save" ? "Saving…" : "Save"}
        </Button>
        {item.configured && vaultEnabled && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy !== null}
            onClick={onDelete}
            title="Delete this credential"
          >
            <Trash2 size={12} />
          </Button>
        )}
      </div>
    </div>
  );
}

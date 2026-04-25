"use client";

import { Avatar } from "@/components/ui/avatar";
import type { User } from "@/types";

interface Props {
  user: User | null;
}

export function ProfilePanel({ user }: Props) {
  if (!user) {
    return (
      <Card>
        <p className="t-body fg-secondary">Not signed in.</p>
      </Card>
    );
  }
  const initials = computeInitials(user.display_name ?? user.email);
  const created = new Date(user.created_at).toLocaleDateString();
  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex items-center gap-4">
          <Avatar tone="blue" size="xl" shape="circle">
            {initials}
          </Avatar>
          <div className="min-w-0 flex-1">
            <h2 className="t-h2 fg-primary truncate">{user.display_name}</h2>
            <p className="t-small fg-tertiary truncate">{user.email}</p>
            <p className="mt-1 text-[11.5px] text-fg-muted">
              Member since {created}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <h3 className="t-h3 fg-primary mb-3">Account</h3>
        <dl className="grid grid-cols-1 gap-3 text-[12.5px] sm:grid-cols-2">
          <Row label="Display name" value={user.display_name} />
          <Row label="Email" value={user.email} mono />
          <Row label="External ID" value={user.external_id} mono />
          <Row label="Created" value={created} />
        </dl>
        <p className="mt-4 text-[11.5px] text-fg-muted">
          Edit your profile from the identity provider — Aviary mirrors what
          your IdP returns at sign-in. Coming soon: in-app overrides for
          display name and avatar.
        </p>
      </Card>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-5">
      {children}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="t-over fg-muted">{label}</dt>
      <dd
        className={
          mono
            ? "t-mono break-all text-[12px] text-fg-secondary"
            : "t-body fg-secondary"
        }
      >
        {value}
      </dd>
    </div>
  );
}

function computeInitials(source: string): string {
  const trimmed = source.trim();
  if (!trimmed) return "?";
  if (trimmed.includes("@")) {
    return trimmed.split("@")[0].slice(0, 2).toUpperCase();
  }
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

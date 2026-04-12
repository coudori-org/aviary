"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Search } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { WorkflowGrid } from "@/features/workflows/components/workflow-grid";
import { workflowsApi } from "@/features/workflows/api/workflows-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import type { Workflow } from "@/types";

export default function WorkflowsPage() {
  const { user } = useAuth();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    setLoading(true);
    workflowsApi
      .list()
      .then((data) => {
        const filtered = search
          ? data.items.filter((w) => w.name.toLowerCase().includes(search.toLowerCase()))
          : data.items;
        setWorkflows(filtered);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [user, search]);

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container px-8 py-8">
        <div className="mb-8 flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="type-heading text-fg-primary">Workflows</h1>
            <p className="mt-1 type-caption text-fg-muted">
              {total} workflow{total !== 1 ? "s" : ""} in your workspace
            </p>
          </div>
          <Link href={routes.workflowNew}>
            <Button variant="cta">
              <Plus size={14} strokeWidth={2.5} />
              New Workflow
            </Button>
          </Link>
        </div>

        <div className="mb-6">
          <div className="relative max-w-md">
            <Search
              size={14}
              strokeWidth={1.75}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-disabled pointer-events-none"
            />
            <Input
              placeholder="Search workflows…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        <WorkflowGrid
          workflows={workflows}
          loading={loading}
          searchActive={!!search}
          emptyAction={
            <Link href={routes.workflowNew}>
              <Button variant="secondary" size="sm">
                Create your first workflow
              </Button>
            </Link>
          }
        />
      </div>
    </div>
  );
}

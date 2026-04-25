"use client";

import Link from "next/link";
import { ChevronRight } from "@/components/icons";
import { routes } from "@/lib/constants/routes";
import type { Workflow } from "@/types";

export interface WorkflowCrumbProps {
  workflow: Workflow;
  /** Trailing segment after the workflow name (e.g. "Detail", "Runs"). */
  trailing?: string;
}

/**
 * Plain-text breadcrumb for the AppShell header slot:
 *   Workflows › Workflow name [› trailing]
 */
export function WorkflowCrumb({ workflow, trailing }: WorkflowCrumbProps) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex min-w-0 items-center gap-2 text-[12.5px]"
    >
      <Link href={routes.workflows} className="text-fg-tertiary hover:text-fg-primary">
        Workflows
      </Link>
      <ChevronRight size={11} className="text-fg-muted shrink-0" />
      {trailing ? (
        <Link
          href={routes.workflow(workflow.id)}
          className="truncate font-medium text-fg-primary hover:underline decoration-fg-muted underline-offset-2"
        >
          {workflow.name}
        </Link>
      ) : (
        <span className="truncate font-medium text-fg-primary">{workflow.name}</span>
      )}
      {trailing && (
        <>
          <ChevronRight size={11} className="text-fg-muted shrink-0" />
          <span className="truncate text-fg-tertiary">{trailing}</span>
        </>
      )}
    </nav>
  );
}

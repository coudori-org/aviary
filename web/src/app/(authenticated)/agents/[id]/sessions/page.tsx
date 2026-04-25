"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { LoadingState } from "@/components/feedback/loading-state";
import { routes } from "@/lib/constants/routes";

/**
 * Legacy `/agents/{id}/sessions` route — sessions now live inside the
 * agent detail's chat tab as a left rail. We keep this path alive for
 * any bookmarks/links and bounce to the new home.
 */
export default function AgentSessionsRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(routes.agentChat(params.id));
  }, [params.id, router]);
  return <LoadingState fullHeight label="Redirecting…" />;
}

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { http } from "@/lib/http";
import { LoadingState } from "@/components/feedback/loading-state";
import { ErrorState } from "@/components/feedback/error-state";
import { ChatView } from "@/features/chat/components/chat-view";
import { routes } from "@/lib/constants/routes";
import type { Session } from "@/types";

/**
 * Legacy session route. Chat sessions now live inside the agent detail
 * (`/agents/{id}?tab=chat&session=...`) — we redirect there. Workflow-
 * origin sessions (no agent_id) stay here and render the bare ChatView
 * so existing deep-links keep working.
 */
export default function SessionRedirect() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [redirecting, setRedirecting] = useState(true);
  const [keepHere, setKeepHere] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    http
      .get<{ session: Session }>(`/sessions/${params.id}`)
      .then((data) => {
        if (!alive) return;
        if (data.session.agent_id) {
          router.replace(routes.agentChat(data.session.agent_id, params.id));
        } else {
          setKeepHere(true);
          setRedirecting(false);
        }
      })
      .catch((e) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        setRedirecting(false);
      });
    return () => {
      alive = false;
    };
  }, [params.id, router]);

  if (error) {
    return <ErrorState title="Couldn't load session" description={error} />;
  }
  if (redirecting) {
    return <LoadingState fullHeight label="Opening session…" />;
  }
  if (keepHere) {
    return <ChatView sessionId={params.id} />;
  }
  return <LoadingState fullHeight label="Opening session…" />;
}

"use client";

import { useParams } from "next/navigation";
import { AgentChatPage } from "@/features/agents/components/detail/agent-chat-page";

export default function AgentPage() {
  const params = useParams<{ id: string }>();
  return <AgentChatPage agentId={params.id} />;
}

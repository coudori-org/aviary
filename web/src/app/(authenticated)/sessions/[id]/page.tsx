"use client";

import { useParams } from "next/navigation";
import { ChatView } from "@/features/chat/components/chat-view";

/**
 * Session/chat page — thin route shell. All logic is in features/chat/.
 *
 * Compare with the previous 570-line god component: this file is 9 lines.
 */
export default function ChatPage() {
  const params = useParams<{ id: string }>();
  return <ChatView sessionId={params.id} />;
}

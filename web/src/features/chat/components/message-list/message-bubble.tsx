import { AlertCircle } from "@/components/icons";
import { UserBubble } from "./user-bubble";
import { AgentBubble } from "./agent-bubble";
import type { FileRef, Message } from "@/types";

interface MessageBubbleProps {
  message: Message;
  showAvatar?: boolean;
}

function UserErrorBubble({ content }: { content: string }) {
  return (
    <div className="flex flex-row-reverse gap-3 animate-fade-in">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-danger/15 text-danger">
        <AlertCircle size={16} />
      </div>
      <div className="max-w-[60%] rounded-xl rounded-tr-sm border border-danger/20 bg-danger/5 px-4 py-3 type-body text-danger">
        {content}
      </div>
    </div>
  );
}

export function MessageBubble({ message, showAvatar = true }: MessageBubbleProps) {
  if (message.metadata?.transient) {
    return <UserErrorBubble content={message.content} />;
  }
  if (message.sender_type === "user") {
    const attachments = message.metadata?.attachments as FileRef[] | undefined;
    return (
      <UserBubble
        content={message.content}
        showAvatar={showAvatar}
        targetId={`${message.id}/user`}
        attachments={attachments}
      />
    );
  }
  return <AgentBubble message={message} showAvatar={showAvatar} />;
}

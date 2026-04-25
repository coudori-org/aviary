"use client";

import { MessageSquare, Plus } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

export interface EmptyChatProps {
  onCreate: () => void;
  creating?: boolean;
  hasSessions: boolean;
}

export function EmptyChat({ onCreate, creating, hasSessions }: EmptyChatProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-6 py-12">
      <div className="grid h-12 w-12 place-items-center rounded-[10px] bg-hover text-fg-tertiary">
        <MessageSquare size={20} />
      </div>
      <div className="text-center">
        <h2 className="t-h2 fg-primary">
          {hasSessions ? "Pick a session" : "Start your first session"}
        </h2>
        <p className="mt-1 max-w-[360px] text-[12.5px] text-fg-muted">
          {hasSessions
            ? "Choose one from the left, or start a new conversation."
            : "Open a fresh chat with this agent to begin."}
        </p>
      </div>
      <Button onClick={onCreate} disabled={creating} size="sm">
        {creating ? (
          <>
            <Spinner size={11} /> Starting…
          </>
        ) : (
          <>
            <Plus size={13} /> New session
          </>
        )}
      </Button>
    </div>
  );
}

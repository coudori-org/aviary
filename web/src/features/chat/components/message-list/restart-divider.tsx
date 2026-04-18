import { RefreshCw } from "@/components/icons";

/**
 * RestartDivider — marks the boundary between two turns that belong to
 * different agent contexts within a single session.
 *
 * Used when the previous assistant turn ended abnormally (error /
 * cancelled) and the next user turn starts fresh — the transcript above
 * the divider is preserved for the user to read but is NOT part of the
 * current turn's SDK context. In the workflow inspector this is what
 * resume looks like: step A failed, the user hit Resume, a new run
 * produced a new user + agent turn in the same shared session.
 */
export function RestartDivider() {
  return (
    <div className="my-4 flex items-center gap-3" role="separator" aria-label="New attempt">
      <div className="h-px flex-1 bg-info/20" />
      <span className="flex items-center gap-1.5 type-caption text-info">
        <RefreshCw size={12} strokeWidth={2} />
        New attempt
      </span>
      <div className="h-px flex-1 bg-info/20" />
    </div>
  );
}

import { cn } from "@/lib/utils";

/**
 * Published reach card — shows how the user's published agents/workflows
 * are being installed by other teams. Marketplace API is not wired yet,
 * so today this renders an empty state. Stage C1 fills it in.
 */
export function PublishedReachCard() {
  return (
    <section
      className={cn(
        "flex flex-col rounded-[10px] border border-border-subtle bg-raised overflow-hidden"
      )}
    >
      <header className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
        <h2 className="t-h3 fg-primary">Published reach</h2>
        <span className="text-[11.5px] text-fg-muted">Coming soon</span>
      </header>
      <div className="px-4 py-8 text-center">
        <div className="t-small fg-tertiary">
          Live install metrics will appear here once Marketplace ships.
        </div>
      </div>
    </section>
  );
}

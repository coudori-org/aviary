import { cn } from "@/lib/utils";
import { Sparkline } from "./sparkline";

export interface StatBreakdownItem {
  label: string;
  value: number | string;
}

export interface StatCardProps {
  label: string;
  value: number | string;
  /** Top-right caption (e.g. "Last 7 days"). */
  sub?: string;
  /** Top-right delta line above sub (e.g. "+12 this week"). */
  delta?: string;
  deltaPositive?: boolean;
  /** Optional 7-day usage trend rendered at the bottom of the card. */
  sparkline?: { data: number[]; color?: string };
  /** Optional secondary metrics (e.g. Published / Installs) shown below
   *  the headline value. Mutually exclusive with `sparkline`. */
  breakdown?: StatBreakdownItem[];
}

export function StatCard({
  label,
  value,
  sub,
  delta,
  deltaPositive,
  sparkline,
  breakdown,
}: StatCardProps) {
  return (
    <div className="rounded-[10px] border border-border-subtle bg-raised p-[14px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="t-small fg-tertiary">{label}</div>
          <div
            className={cn(
              "num mt-[2px] text-[28px] font-semibold leading-tight",
              "tracking-[-0.015em] text-fg-primary",
            )}
          >
            {value}
          </div>
        </div>
        {(delta || sub) && (
          <div className="text-right shrink-0">
            {delta && (
              <div
                className={cn(
                  "num text-[11.5px] font-semibold",
                  deltaPositive ? "text-status-live" : "text-fg-tertiary",
                )}
              >
                {delta}
              </div>
            )}
            {sub && <div className="mt-[2px] text-[10.5px] text-fg-muted">{sub}</div>}
          </div>
        )}
      </div>

      {sparkline && (
        <div className="mt-3">
          <Sparkline data={sparkline.data} color={sparkline.color} />
        </div>
      )}

      {breakdown && breakdown.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border-subtle pt-3">
          {breakdown.map((item) => (
            <div key={item.label}>
              <div className="t-over fg-muted">{item.label}</div>
              <div className="num mt-[2px] text-[16px] font-semibold text-fg-primary">
                {item.value}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

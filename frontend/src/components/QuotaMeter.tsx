import { Gauge } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useLimits } from "@/lib/limitsContext";
import { cn } from "@/lib/utils";
import type { LimitsStatus } from "@/lib/types";

/**
 * Compact quota meter for the top header. Shows hour + day usage with a thin
 * progress strip; click to see the month line + reset times.
 */
export function QuotaMeter() {
  const { status } = useLimits();
  if (!status) return null;

  const hourRatio = ratio(status.usage.hour, status.limits.max_per_hour);
  const dayRatio = ratio(status.usage.day, status.limits.max_per_day);
  const worst = Math.max(hourRatio, dayRatio);
  const tone = worst >= 1 ? "danger" : worst >= 0.8 ? "warn" : "ok";

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "group flex items-center gap-2 rounded-full border border-border bg-card/70 px-3 py-1.5 text-xs font-medium ring-focus hover:bg-card",
            tone === "warn" && "border-amber-500/40",
            tone === "danger" && "border-red-500/50 text-red-700 dark:text-red-400"
          )}
          aria-label="Usage and limits"
        >
          <Gauge
            className={cn(
              "h-3.5 w-3.5 text-muted-foreground",
              tone === "warn" && "text-amber-600 dark:text-amber-400",
              tone === "danger" && "text-red-600 dark:text-red-400"
            )}
          />
          <span className="tabular-nums">
            {status.usage.hour}/{status.limits.max_per_hour}
          </span>
          <span className="text-muted-foreground">This Hour</span>
          <span className="text-border">·</span>
          <span className="tabular-nums">
            {status.usage.day}/{status.limits.max_per_day}
          </span>
          <span className="text-muted-foreground">Today</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Your Extraction Quota
        </div>
        <div className="space-y-4">
          <Line label="This Hour" status={status} scope="hour" />
          <Line label="Today" status={status} scope="day" />
          <Line label="This Month" status={status} scope="month" />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Line({
  label,
  status,
  scope,
}: {
  label: string;
  status: LimitsStatus;
  scope: "hour" | "day" | "month";
}) {
  const cap =
    scope === "hour"
      ? status.limits.max_per_hour
      : scope === "day"
      ? status.limits.max_per_day
      : status.limits.max_per_month;
  const used = status.usage[scope];
  const r = ratio(used, cap);
  const tone = r >= 1 ? "danger" : r >= 0.8 ? "warn" : "ok";
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span>{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {used} / {cap}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            tone === "ok" && "bg-foreground/80",
            tone === "warn" && "bg-amber-500",
            tone === "danger" && "bg-red-500"
          )}
          style={{ width: `${Math.min(100, r * 100)}%` }}
        />
      </div>
      <div className="mt-1 text-[10px] text-muted-foreground">
        Resets {formatReset(status.reset_at[scope])}
      </div>
    </div>
  );
}

function ratio(used: number, cap: number): number {
  if (cap <= 0) return 0;
  return used / cap;
}

function formatReset(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = d.getTime() - now.getTime();
    const mins = Math.max(0, Math.round(diff / 60000));
    if (mins < 60) return `in ${mins} min`;
    const hrs = Math.round(mins / 60);
    if (hrs < 48) return `in ${hrs} hr`;
    const days = Math.round(hrs / 24);
    return `in ${days} d`;
  } catch {
    return "soon";
  }
}

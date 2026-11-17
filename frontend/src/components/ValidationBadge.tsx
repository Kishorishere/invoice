import { CheckCircle2, CircleHelp, XCircle } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ValidationCheck } from "@/lib/types";
import { cn } from "@/lib/utils";

const PRETTY: Record<string, string> = {
  items_present: "Line items",
  subtotal_matches_items: "Subtotal",
  vat_computed_correctly: "VAT",
  total_equals_subtotal_plus_vat: "Total",
  dates_sensible: "Dates",
};

export function ValidationBadge({ check }: { check: ValidationCheck }) {
  const name = PRETTY[check.name] ?? check.name;
  const { icon, cls } =
    check.status === "pass"
      ? { icon: <CheckCircle2 className="h-3.5 w-3.5" />, cls: "bg-success/10 text-success" }
      : check.status === "fail"
        ? { icon: <XCircle className="h-3.5 w-3.5" />, cls: "bg-destructive/10 text-destructive" }
        : { icon: <CircleHelp className="h-3.5 w-3.5" />, cls: "bg-muted text-muted-foreground" };

  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium cursor-help transition-colors",
              cls
            )}
          >
            {icon}
            {name}
            {check.delta != null && check.status === "fail" && (
              <span className="font-mono opacity-80">
                Δ {check.delta > 0 ? "+" : ""}
                {check.delta.toFixed(2)}
              </span>
            )}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-xs">
          <p className="text-xs">{check.message}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

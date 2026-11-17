import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, copyToClipboard } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number | null | undefined;
  mono?: boolean;
  className?: string;
}

export function CopyField({ label, value, mono, className }: Props) {
  const [copied, setCopied] = useState(false);
  const display =
    value == null || value === ""
      ? "—"
      : typeof value === "number"
        ? value.toLocaleString("en-US", { maximumFractionDigits: 2 })
        : String(value);
  const copyable = display !== "—";

  const onCopy = async () => {
    const ok = await copyToClipboard(display);
    if (ok) {
      setCopied(true);
      toast.success(`Copied ${label.toLowerCase()}`);
      setTimeout(() => setCopied(false), 1400);
    } else {
      toast.error("Couldn't copy to clipboard");
    }
  };

  return (
    <div
      className={cn(
        "group flex items-start justify-between gap-3 rounded-xl border border-transparent px-3 py-2.5 transition-colors hover:border-border hover:bg-muted/50",
        className
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div
          className={cn(
            "mt-0.5 break-words text-sm text-foreground",
            mono && "font-mono",
            display === "—" && "text-muted-foreground"
          )}
        >
          {display}
        </div>
      </div>
      {copyable && (
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onCopy}
                aria-label={`Copy ${label}`}
                className="relative mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-lg text-muted-foreground opacity-0 transition-all hover:bg-background hover:text-foreground group-hover:opacity-100 ring-focus"
              >
                <AnimatePresence mode="wait" initial={false}>
                  {copied ? (
                    <motion.span
                      key="check"
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.6, opacity: 0 }}
                      transition={{ type: "spring", stiffness: 500, damping: 24 }}
                      className="text-success"
                    >
                      <Check className="h-4 w-4" />
                    </motion.span>
                  ) : (
                    <motion.span
                      key="copy"
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.6, opacity: 0 }}
                      transition={{ type: "spring", stiffness: 500, damping: 24 }}
                    >
                      <Copy className="h-4 w-4" />
                    </motion.span>
                  )}
                </AnimatePresence>
              </button>
            </TooltipTrigger>
            <TooltipContent>Copy to clipboard</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

const STEPS = [
  { label: "Reading your image", delay: 0 },
  { label: "Asking the AI", delay: 900 },
  { label: "Checking the math", delay: 2400 },
  { label: "Almost done", delay: 3600 },
];

export function ExtractionStepper() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const timers = STEPS.map((s, i) =>
      window.setTimeout(() => setStep((cur) => Math.max(cur, i)), s.delay)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-soft">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">Running Gemini</p>
      <ol className="mt-4 space-y-2.5">
        {STEPS.map((s, i) => {
          const done = i < step;
          const active = i === step;
          return (
            <li key={s.label} className="flex items-center gap-3">
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border transition-all",
                  done
                    ? "border-success bg-success text-success-foreground"
                    : active
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-muted text-muted-foreground"
                )}
              >
                {done ? (
                  <Check className="h-3.5 w-3.5" />
                ) : active ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
              </span>
              <motion.span
                className={cn(
                  "text-sm transition-colors",
                  done || active ? "text-foreground" : "text-muted-foreground"
                )}
                animate={{ opacity: done || active ? 1 : 0.6 }}
              >
                {s.label}
              </motion.span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

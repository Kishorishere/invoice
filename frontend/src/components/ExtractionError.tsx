import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  message: string;
  onRetry: () => void;
}

export function ExtractionError({ message, onRetry }: Props) {
  return (
    <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-5 shadow-soft animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
          <AlertTriangle className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-foreground">
            Gemini couldn't extract this one
          </h3>
          <p className="mt-1 text-sm text-muted-foreground text-balance">{message}</p>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button onClick={onRetry} size="sm">
              <RefreshCw className="h-4 w-4" />
              Try again
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

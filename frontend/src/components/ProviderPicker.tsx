import { useEffect, useMemo, useState } from "react";
import { Check, Loader2, Pencil, RefreshCw } from "lucide-react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ApiError } from "@/lib/api";
import { fetchModels, getCached, invalidate } from "@/lib/modelCache";
import type { ModelInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

const PROVIDER = "gemini";
const PROVIDER_LABEL = "Google";

interface Props {
  model: string | null;
  onModelChange: (m: string) => void;
  disabled?: boolean;
}

type ModelsStatus =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; models: ModelInfo[]; default: string | null }
  | { kind: "err"; message: string };

/**
 * One trigger: "Model: <label> (Google)" + pencil. Opens a popover with a
 * searchable list of Gemini models.
 */
export function ProviderPicker({ model, onModelChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ModelsStatus>(() => fromCache());

  useEffect(() => {
    const cached = getCached(PROVIDER);
    if (cached) {
      setStatus({ kind: "ok", models: cached.models, default: cached.default });
      return;
    }
    let cancelled = false;
    setStatus({ kind: "loading" });
    fetchModels(PROVIDER)
      .then((resp) => {
        if (cancelled) return;
        setStatus({ kind: "ok", models: resp.models, default: resp.default });
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus({
          kind: "err",
          message: err instanceof ApiError ? err.message : "Couldn't load models.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const label = useMemo(() => resolveLabel(model, status), [model, status]);

  const refresh = async () => {
    invalidate(PROVIDER);
    setStatus({ kind: "loading" });
    try {
      const resp = await fetchModels(PROVIDER);
      setStatus({ kind: "ok", models: resp.models, default: resp.default });
    } catch (err) {
      setStatus({
        kind: "err",
        message: err instanceof ApiError ? err.message : "Couldn't load models.",
      });
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            "group inline-flex max-w-full items-center gap-2 rounded-full border border-border bg-background/60 px-3.5 py-1.5 text-xs font-medium text-foreground shadow-soft backdrop-blur transition-colors",
            "hover:bg-card hover:border-border/80 ring-focus",
            "disabled:cursor-not-allowed disabled:opacity-60"
          )}
          aria-label="Change model"
        >
          <span className="text-muted-foreground">Model:</span>
          <span className="truncate">
            {label} <span className="text-muted-foreground">({PROVIDER_LABEL})</span>
          </span>
          <Pencil className="h-3 w-3 text-muted-foreground transition-transform group-hover:rotate-6" />
        </button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-[22rem] p-0">
        <Command loop shouldFilter>
          <CommandInput placeholder="Search Gemini models…" />
          <CommandList>
            {status.kind === "loading" && (
              <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading models…
              </div>
            )}
            {status.kind === "err" && (
              <div className="px-3 py-4 text-sm">
                <p className="text-destructive text-balance">{status.message}</p>
                <button
                  type="button"
                  onClick={refresh}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-foreground hover:bg-muted ring-focus"
                >
                  <RefreshCw className="h-3 w-3" /> Try again
                </button>
              </div>
            )}
            {status.kind === "ok" && (
              <>
                <CommandEmpty>No models match that search.</CommandEmpty>
                <CommandGroup
                  heading={`${status.models.length} model${status.models.length === 1 ? "" : "s"}`}
                >
                  {status.models.map((m) => {
                    const selected = model === m.id;
                    const isDefault = status.default === m.id;
                    return (
                      <CommandItem
                        key={m.id}
                        value={`${m.id} ${m.label}`}
                        onSelect={() => {
                          onModelChange(m.id);
                          setOpen(false);
                        }}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 truncate text-sm font-medium">
                            {m.label}
                            {isDefault && (
                              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
                                default
                              </span>
                            )}
                          </div>
                          <div className="truncate font-mono text-[10px] text-muted-foreground">
                            {m.id}
                          </div>
                        </div>
                        <Check
                          className={cn(
                            "h-4 w-4 shrink-0 text-foreground transition-opacity",
                            selected ? "opacity-100" : "opacity-0"
                          )}
                        />
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
                <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
                  <span>Cached · server + browser</span>
                  <button
                    type="button"
                    onClick={refresh}
                    className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 hover:bg-muted hover:text-foreground ring-focus"
                  >
                    <RefreshCw className="h-3 w-3" /> Refresh
                  </button>
                </div>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function fromCache(): ModelsStatus {
  const cached = getCached(PROVIDER);
  if (cached) return { kind: "ok", models: cached.models, default: cached.default };
  return { kind: "idle" };
}

function resolveLabel(model: string | null, status: ModelsStatus): string {
  if (status.kind === "ok") {
    const target = model ?? status.default;
    if (target) {
      const found = status.models.find((m) => m.id === target);
      if (found) return found.label;
      return humanize(target);
    }
  }
  if (model) return humanize(model);
  if (status.kind === "loading") return "Loading…";
  return "Gemini";
}

function humanize(id: string): string {
  const tail = id.split("/").slice(-1)[0];
  return tail
    .split("-")
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

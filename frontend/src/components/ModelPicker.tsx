import { useEffect, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Loader2, RefreshCw, Sparkles } from "lucide-react";

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

interface Props {
  provider: string;
  value: string | null;
  onChange: (modelId: string) => void;
}

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; models: ModelInfo[]; default: string | null }
  | { kind: "err"; message: string };

export function ModelPicker({ provider, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>(() => fromCache(provider));

  // When provider changes, reset to that provider's cached entry (or idle).
  useEffect(() => {
    setStatus(fromCache(provider));
  }, [provider]);

  const load = async () => {
    setStatus({ kind: "loading" });
    try {
      const resp = await fetchModels(provider);
      setStatus({ kind: "ok", models: resp.models, default: resp.default });
      if (!value && resp.default) onChange(resp.default);
    } catch (err) {
      setStatus({
        kind: "err",
        message: err instanceof ApiError ? err.message : "Couldn't load models.",
      });
    }
  };

  const refresh = async (e?: React.MouseEvent) => {
    e?.stopPropagation();
    invalidate(provider);
    await load();
  };

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next && status.kind === "idle") load();
  };

  const label = value ?? (status.kind === "ok" ? status.default ?? "Pick model" : "Pick model");

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex max-w-[16rem] items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-soft transition-colors hover:bg-muted ring-focus"
          title={label}
        >
          <Sparkles className="h-3 w-3 text-primary" />
          <span className="truncate font-mono">{shortLabel(label)}</span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[20rem] p-0">
        <Command loop shouldFilter>
          <CommandInput placeholder={`Search ${provider} models…`} />
          <CommandList>
            {status.kind === "loading" && (
              <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading models…
              </div>
            )}

            {status.kind === "err" && (
              <div className="px-3 py-4 text-sm">
                <div className="flex items-start gap-2 text-destructive">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p className="text-balance">{status.message}</p>
                </div>
                <button
                  type="button"
                  onClick={refresh}
                  className="mt-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-primary hover:bg-primary/10 ring-focus"
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
                    const selected = value === m.id;
                    const isDefault = status.default === m.id;
                    return (
                      <CommandItem
                        key={m.id}
                        value={`${m.id} ${m.label}`}
                        onSelect={() => {
                          onChange(m.id);
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
                            "h-4 w-4 shrink-0 text-primary transition-opacity",
                            selected ? "opacity-100" : "opacity-0"
                          )}
                        />
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
                <div className="flex items-center justify-between border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
                  <span>Cached for 24h &middot; server + browser</span>
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

function fromCache(provider: string): Status {
  const cached = getCached(provider);
  if (cached) return { kind: "ok", models: cached.models, default: cached.default };
  return { kind: "idle" };
}

function shortLabel(label: string): string {
  const tail = label.split("/").slice(-1)[0];
  return tail.length > 24 ? tail.slice(0, 22) + "…" : tail;
}

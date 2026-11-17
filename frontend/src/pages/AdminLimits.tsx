import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";

import { AppLayout } from "@/components/AppLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import { useLimits } from "@/lib/limitsContext";
import type { LimitsConfig } from "@/lib/types";

const FIELDS: { key: keyof LimitsConfig; label: string; help: string }[] = [
  {
    key: "max_files_per_upload",
    label: "Files per upload",
    help: "How many invoices a user can drop at once.",
  },
  {
    key: "max_per_hour",
    label: "Extractions per hour",
    help: "Per-user rolling 60-minute cap.",
  },
  {
    key: "max_per_day",
    label: "Extractions per day",
    help: "Per-user rolling 24-hour cap. Must be ≥ hourly.",
  },
  {
    key: "max_per_month",
    label: "Extractions per month",
    help: "Per-user rolling 30-day cap. Must be ≥ daily.",
  },
];

export function AdminLimits() {
  const { status, refresh: refreshMine } = useLimits();
  const [form, setForm] = useState<LimitsConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const cfg = await api.getAdminLimits();
      setForm(cfg);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load limits.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      await api.setAdminLimits(form);
      toast.success("Limits updated.");
      await Promise.all([load(), refreshMine()]);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Couldn't save limits.";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout>
      <div className="mx-auto max-w-3xl pt-6 sm:pt-10 animate-fade-in">
        <header className="mb-6">
          <h1 className="font-display text-4xl sm:text-5xl">Limits</h1>
          <p className="mt-1 text-muted-foreground">
            One set of numbers for everyone. Each user gets their own rolling pool
            against these caps.
          </p>
        </header>

        {error && (
          <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {status && (
          <div className="mb-6 rounded-2xl border border-border bg-card p-4 text-sm shadow-soft">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Your Current Usage
            </div>
            <div className="grid grid-cols-3 gap-4">
              <UsageCell
                label="This Hour"
                used={status.usage.hour}
                cap={status.limits.max_per_hour}
              />
              <UsageCell
                label="Today"
                used={status.usage.day}
                cap={status.limits.max_per_day}
              />
              <UsageCell
                label="This Month"
                used={status.usage.month}
                cap={status.limits.max_per_month}
              />
            </div>
          </div>
        )}

        {form && (
          <form
            onSubmit={onSubmit}
            className="space-y-5 rounded-2xl border border-border bg-card p-6 shadow-soft"
          >
            {FIELDS.map((f) => (
              <div key={f.key} className="space-y-1.5">
                <Label htmlFor={f.key}>{f.label}</Label>
                <Input
                  id={f.key}
                  type="number"
                  min={1}
                  value={form[f.key]}
                  onChange={(e) =>
                    setForm((cur) =>
                      cur ? { ...cur, [f.key]: Math.max(1, Number(e.target.value) || 1) } : cur
                    )
                  }
                  className="max-w-xs"
                />
                <p className="text-xs text-muted-foreground">{f.help}</p>
              </div>
            ))}

            <div className="flex items-center justify-end gap-2 pt-2">
              <Button type="button" variant="ghost" onClick={() => void load()} disabled={saving}>
                Discard
              </Button>
              <Button type="submit" disabled={saving}>
                <Save className="h-4 w-4" />
                {saving ? "Saving…" : "Save limits"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </AppLayout>
  );
}

function UsageCell({ label, used, cap }: { label: string; used: number; cap: number }) {
  const r = cap > 0 ? used / cap : 0;
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">
        {used}
        <span className="text-sm font-normal text-muted-foreground"> / {cap}</span>
      </div>
      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={
            r >= 1
              ? "h-full bg-red-500"
              : r >= 0.8
              ? "h-full bg-amber-500"
              : "h-full bg-foreground/70"
          }
          style={{ width: `${Math.min(100, r * 100)}%` }}
        />
      </div>
    </div>
  );
}

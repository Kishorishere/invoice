import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import confetti from "canvas-confetti";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Copy as CopyIcon,
  Loader2,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { AppLayout } from "@/components/AppLayout";
import { ExtractionError } from "@/components/ExtractionError";
import { ExtractionStepper } from "@/components/ExtractionStepper";
import { InvoiceResults } from "@/components/InvoiceResults";
import { Uploader } from "@/components/Uploader";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useInvoices } from "@/lib/invoicesContext";
import { useLimits } from "@/lib/limitsContext";
import { cn, formatCurrency, relativeTime } from "@/lib/utils";
import type { DuplicateDetail, ExtractResponse, QuotaExceededDetail } from "@/lib/types";

const DEFAULT_MODEL = "gemini-3.5-flash";

const modelKey = (email: string) => `invoice.ai:model:${email}:gemini`;

// Bump when a default changes and you want previously-persisted selections
// cleared so the new default takes effect on next load. Any user who had
// made an explicit pick will re-pick; everyone else just gets the new default.
const MODEL_DEFAULTS_VERSION = "2";
const MODEL_DEFAULTS_VERSION_KEY = "invoice.ai:model-defaults-version";

if (typeof window !== "undefined") {
  const current = localStorage.getItem(MODEL_DEFAULTS_VERSION_KEY);
  if (current !== MODEL_DEFAULTS_VERSION) {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith("invoice.ai:model:")) localStorage.removeItem(k);
    }
    localStorage.setItem(MODEL_DEFAULTS_VERSION_KEY, MODEL_DEFAULTS_VERSION);
  }
}

type ItemStatus = "pending" | "running" | "done" | "error" | "blocked" | "duplicate";

interface QueueItem {
  id: string;
  file: File;
  status: ItemStatus;
  previewUrl: string | null;
  result?: ExtractResponse;
  errorMsg?: string;
  blockedUntil?: string; // ISO
  duplicate?: DuplicateDetail;
}

function makeItem(file: File): QueueItem {
  const id = `${file.name}:${file.size}:${file.lastModified}:${Math.random().toString(36).slice(2, 7)}`;
  return {
    id,
    file,
    status: "pending",
    previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
  };
}

export function Dashboard() {
  const { refresh: refreshInvoices } = useInvoices();
  const { refresh: refreshLimits } = useLimits();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [currentModel, setCurrentModel] = useState<string | null>(null);

  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);

  // Hydrate the model for this user.
  useEffect(() => {
    if (!user) return;
    setCurrentModel((cur) => {
      if (cur) return cur;
      const saved = localStorage.getItem(modelKey(user.email));
      return saved ?? DEFAULT_MODEL;
    });
  }, [user]);

  // Clean up object URLs on unmount.
  useEffect(() => {
    return () => {
      for (const item of queue) {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setModel = (id: string) => {
    setCurrentModel(id);
    if (user) localStorage.setItem(modelKey(user.email), id);
  };

  const setFiles = (nextFiles: File[]) => {
    setQueue((cur) => {
      // Preserve existing items (and their previews / results); add new ones.
      const byKey = new Map(cur.map((q) => [fileKey(q.file), q] as const));
      const keep = new Set(nextFiles.map((f) => fileKey(f)));
      // Revoke previews for files being removed.
      for (const item of cur) {
        if (!keep.has(fileKey(item.file)) && item.previewUrl) {
          URL.revokeObjectURL(item.previewUrl);
        }
      }
      return nextFiles.map((f) => byKey.get(fileKey(f)) ?? makeItem(f));
    });
  };

  const removeItem = (id: string) => {
    setQueue((cur) => {
      const gone = cur.find((q) => q.id === id);
      if (gone?.previewUrl) URL.revokeObjectURL(gone.previewUrl);
      return cur.filter((q) => q.id !== id);
    });
  };

  const clearAll = () => {
    for (const item of queue) {
      if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
    }
    setQueue([]);
  };

  const runBatch = async () => {
    if (!queue.length) {
      toast.error("Pick at least one file.");
      return;
    }
    setRunning(true);
    let anyOk = false;

    for (const item of queue) {
      if (item.status === "done" || item.status === "error") continue;

      setQueue((cur) =>
        cur.map((q) => (q.id === item.id ? { ...q, status: "running" } : q))
      );

      try {
        const resp = await api.extract(item.file, currentModel);
        anyOk = true;
        setQueue((cur) =>
          cur.map((q) =>
            q.id === item.id ? { ...q, status: "done", result: resp } : q
          )
        );
        void refreshInvoices();
        void refreshLimits();
      } catch (err) {
        if (err instanceof ApiError && err.status === 429) {
          const detail = err.detail as QuotaExceededDetail | undefined;
          const scope = detail?.scope ?? "hour";
          const resetAt = detail?.reset_at;
          toast.error(
            `${capitalize(scope)}ly limit reached${
              resetAt ? ` — resumes ${formatReset(resetAt)}` : ""
            }. The rest of the queue is paused.`
          );
          // Mark this item blocked; leave the rest pending.
          setQueue((cur) =>
            cur.map((q) =>
              q.id === item.id ? { ...q, status: "blocked", blockedUntil: resetAt } : q
            )
          );
          void refreshLimits();
          break; // stop the loop — don't burn more requests against a full window
        }
        if (err instanceof ApiError && err.status === 409) {
          // Per-user dedupe: this file is already in the user's history.
          // Mark the item and keep the batch moving — the user decides later
          // whether to open the existing or extract anyway.
          const detail = err.detail as DuplicateDetail | undefined;
          setQueue((cur) =>
            cur.map((q) =>
              q.id === item.id
                ? { ...q, status: "duplicate", duplicate: detail }
                : q
            )
          );
          continue;
        }
        const msg =
          err instanceof ApiError ? err.message : "Something went wrong talking to the server.";
        setQueue((cur) =>
          cur.map((q) => (q.id === item.id ? { ...q, status: "error", errorMsg: msg } : q))
        );
      }
    }

    setRunning(false);
    if (anyOk) {
      const allPass =
        queue.every((q) => q.status === "done" && q.result?.validation.all_pass !== false);
      if (allPass) celebrate();
    }
  };

  const counts = useMemo(() => countByStatus(queue), [queue]);
  const idle = queue.length === 0;
  const allSettled =
    queue.length > 0 &&
    !running &&
    queue.every(
      (q) =>
        q.status === "done" ||
        q.status === "error" ||
        q.status === "blocked" ||
        q.status === "duplicate"
    );
  const hasResults = queue.some(
    (q) =>
      q.status === "done" ||
      q.status === "error" ||
      q.status === "blocked" ||
      q.status === "duplicate" ||
      q.status === "running"
  );

  return (
    <AppLayout>
      <div className="mx-auto max-w-5xl pt-2 animate-fade-in">
        {idle && (
          <header className="mb-8">
            <h1 className="font-sans text-xl font-semibold leading-tight tracking-tight text-foreground sm:text-2xl">
              Invoices, made effortless.
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Upload your invoices and let AI extract the details for you.
            </p>
          </header>
        )}

        {hasResults && (
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <h1 className="font-sans text-xl font-semibold tracking-tight sm:text-2xl">
                {running
                  ? "Reading your invoices…"
                  : allSettled
                  ? summaryLine(counts)
                  : "Queued."}
              </h1>
              {!running && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {counts.done} Done &middot; {counts.error} Failed &middot; {counts.blocked} Blocked &middot; {counts.duplicate} Duplicate &middot; {counts.pending} Pending
                </p>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={clearAll} disabled={running}>
              New batch
            </Button>
          </div>
        )}

        {!hasResults && (
          <div className="space-y-6">
            <Uploader
              busy={running}
              files={queue.map((q) => q.file)}
              onFilesChange={setFiles}
              model={currentModel}
              onModelChange={setModel}
            />
            {queue.length > 0 && (
              <div className="flex justify-end">
                <Button size="lg" onClick={runBatch} className="rounded-full px-8">
                  Extract {queue.length} {queue.length === 1 ? "invoice" : "invoices"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Per-item results stack */}
        {hasResults && (
          <div className="space-y-6">
            <AnimatePresence initial={false}>
              {queue.map((item) => (
                <motion.div
                  key={item.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                >
                  <ItemCard
                    item={item}
                    onRetry={() => retryOne(item, currentModel, setQueue, refreshInvoices, refreshLimits)}
                    onForce={() =>
                      retryOne(item, currentModel, setQueue, refreshInvoices, refreshLimits, { force: true })
                    }
                    onOpenExisting={(id) => navigate(`/invoice/${id}`)}
                    onRemove={() => removeItem(item.id)}
                    disabled={running}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function ItemCard({
  item,
  onRetry,
  onForce,
  onOpenExisting,
  onRemove,
  disabled,
}: {
  item: QueueItem;
  onRetry: () => void;
  onForce: () => void;
  onOpenExisting: (id: string) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  if (item.status === "done" && item.result) {
    return (
      <section>
        <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          <span className="truncate font-medium text-foreground">{item.file.name}</span>
        </div>
        <InvoiceResults response={item.result} imageSrc={item.previewUrl} />
      </section>
    );
  }
  if (item.status === "running") {
    return (
      <section className="rounded-2xl border border-border bg-card p-5 shadow-soft">
        <div className="mb-3 flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin text-foreground/70" />
          <span className="truncate font-medium">{item.file.name}</span>
        </div>
        <ExtractionStepper />
      </section>
    );
  }
  if (item.status === "error") {
    return (
      <section className="space-y-3">
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle className="h-4 w-4" />
          <span className="truncate font-medium">{item.file.name}</span>
        </div>
        <ExtractionError
          message={item.errorMsg ?? "Something went wrong."}
          onRetry={onRetry}
        />
      </section>
    );
  }
  if (item.status === "blocked") {
    return (
      <StatusRow
        icon={<Clock className="h-4 w-4 text-amber-500" />}
        tone="warn"
        file={item.file.name}
        label={
          item.blockedUntil
            ? `Blocked by rate limit — retry ${formatReset(item.blockedUntil)}`
            : "Blocked by rate limit."
        }
        onRemove={onRemove}
        disabled={disabled}
      />
    );
  }
  if (item.status === "duplicate" && item.duplicate) {
    return (
      <DuplicateCard
        fileName={item.file.name}
        detail={item.duplicate}
        onOpenExisting={() => onOpenExisting(item.duplicate!.duplicate_of)}
        onForce={onForce}
        onSkip={onRemove}
        disabled={disabled}
      />
    );
  }
  return (
    <StatusRow
      icon={<Clock className="h-4 w-4 text-muted-foreground" />}
      tone="muted"
      file={item.file.name}
      label="Waiting…"
      onRemove={onRemove}
      disabled={disabled}
    />
  );
}

function DuplicateCard({
  fileName,
  detail,
  onOpenExisting,
  onForce,
  onSkip,
  disabled,
}: {
  fileName: string;
  detail: DuplicateDetail;
  onOpenExisting: () => void;
  onForce: () => void;
  onSkip: () => void;
  disabled: boolean;
}) {
  const supplier = detail.supplier_name ?? "Unknown supplier";
  const amount =
    detail.total_amount != null
      ? formatCurrency(detail.total_amount, detail.currency ?? "NPR")
      : null;
  const invoiceNo = detail.invoice_number;
  const uploaded = relativeTime(detail.uploaded_at);

  return (
    <section
      className={cn(
        "rounded-2xl border border-amber-500/30 bg-amber-50/40 p-5 shadow-soft",
        "dark:border-amber-500/30 dark:bg-amber-500/5"
      )}
      role="group"
      aria-label={`Duplicate of ${fileName}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex h-8 w-8 flex-none items-center justify-center rounded-full",
            "bg-amber-500/15 text-amber-600 dark:text-amber-400"
          )}
          aria-hidden="true"
        >
          <CopyIcon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              Already in your history
            </h3>
            <span className="truncate text-xs text-muted-foreground">
              {fileName}
            </span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-medium text-foreground">{supplier}</span>
            {amount && (
              <>
                <span className="text-muted-foreground">&middot;</span>
                <span className="tabular-nums text-foreground">{amount}</span>
              </>
            )}
            {invoiceNo && (
              <>
                <span className="text-muted-foreground">&middot;</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {invoiceNo}
                </span>
              </>
            )}
          </div>

          <p className="mt-1 text-xs text-muted-foreground">
            Uploaded {uploaded}
            {detail.all_checks_pass ? " · all checks passed" : null}
          </p>

          <p className="mt-3 text-sm text-muted-foreground">
            This won't count against your quota unless you extract it again.
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={onOpenExisting}
              disabled={disabled}
              className="rounded-full"
            >
              Open existing
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onForce}
              disabled={disabled}
              className="rounded-full"
              title="Re-run the AI on this file (counts against your quota)"
            >
              Extract again
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onSkip}
              disabled={disabled}
              className="rounded-full text-muted-foreground"
            >
              <XCircle className="mr-1 h-3.5 w-3.5" />
              Skip
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

function StatusRow({
  icon,
  tone,
  file,
  label,
  onRemove,
  disabled,
}: {
  icon: React.ReactNode;
  tone: "muted" | "warn";
  file: string;
  label: string;
  onRemove: () => void;
  disabled: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-2xl border border-border/60 bg-card/60 px-4 py-3 text-sm shadow-soft",
        tone === "warn" && "border-amber-500/40"
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {icon}
        <span className="truncate font-medium">{file}</span>
        <span className="truncate text-muted-foreground">{"— "}{label}</span>
      </div>
      <Button variant="ghost" size="sm" onClick={onRemove} disabled={disabled}>
        Remove
      </Button>
    </div>
  );
}

async function retryOne(
  item: QueueItem,
  model: string | null,
  setQueue: React.Dispatch<React.SetStateAction<QueueItem[]>>,
  refreshInvoices: () => Promise<void>,
  refreshLimits: () => Promise<void>,
  options: { force?: boolean } = {}
) {
  setQueue((cur) =>
    cur.map((q) =>
      q.id === item.id
        ? { ...q, status: "running", errorMsg: undefined, duplicate: undefined }
        : q
    )
  );
  try {
    const resp = await api.extract(item.file, model, options);
    setQueue((cur) =>
      cur.map((q) => (q.id === item.id ? { ...q, status: "done", result: resp } : q))
    );
    void refreshInvoices();
    void refreshLimits();
  } catch (err) {
    if (err instanceof ApiError && err.status === 429) {
      const detail = err.detail as QuotaExceededDetail | undefined;
      const scope = detail?.scope ?? "hour";
      toast.error(`${capitalize(scope)}ly limit reached.`);
      setQueue((cur) =>
        cur.map((q) =>
          q.id === item.id ? { ...q, status: "blocked", blockedUntil: detail?.reset_at } : q
        )
      );
      void refreshLimits();
      return;
    }
    if (err instanceof ApiError && err.status === 409) {
      const detail = err.detail as DuplicateDetail | undefined;
      setQueue((cur) =>
        cur.map((q) =>
          q.id === item.id ? { ...q, status: "duplicate", duplicate: detail } : q
        )
      );
      return;
    }
    const msg = err instanceof ApiError ? err.message : "Something went wrong.";
    setQueue((cur) => cur.map((q) => (q.id === item.id ? { ...q, status: "error", errorMsg: msg } : q)));
  }
}

function fileKey(f: File): string {
  return `${f.name}:${f.size}:${f.lastModified}`;
}

function countByStatus(queue: QueueItem[]) {
  const c = { pending: 0, running: 0, done: 0, error: 0, blocked: 0, duplicate: 0 };
  for (const q of queue) c[q.status]++;
  return c;
}

function summaryLine(counts: ReturnType<typeof countByStatus>): string {
  const total = counts.done + counts.error + counts.blocked + counts.duplicate;
  if (counts.error === 0 && counts.blocked === 0 && counts.duplicate === 0) {
    return `All ${counts.done} Done.`;
  }
  return `${counts.done} of ${total} Done.`;
}

function capitalize(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1) : s;
}

function formatReset(iso: string): string {
  try {
    const d = new Date(iso);
    const mins = Math.max(0, Math.round((d.getTime() - Date.now()) / 60000));
    if (mins < 60) return `in ${mins} min`;
    const hrs = Math.round(mins / 60);
    return hrs < 48 ? `in ${hrs} hr` : `in ${Math.round(hrs / 24)} d`;
  } catch {
    return "soon";
  }
}

function celebrate() {
  const root = getComputedStyle(document.documentElement);
  const hsl = (name: string) => `hsl(${root.getPropertyValue(name).trim()})`;
  confetti({
    particleCount: 50,
    spread: 60,
    origin: { x: 0.5, y: 0.15 },
    colors: [hsl("--primary"), hsl("--foreground"), hsl("--success"), hsl("--warning")],
    scalar: 0.8,
    ticks: 110,
  });
}

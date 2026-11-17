import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  FileText,
  Image as ImageIcon,
  Search,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { AppLayout } from "@/components/AppLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { useDebouncedValue } from "@/lib/hooks";
import { useInvoices } from "@/lib/invoicesContext";
import type { InvoiceListItem } from "@/lib/types";
import { cn, formatCurrency, formatDate, relativeTime } from "@/lib/utils";

const GROUP_ORDER = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Previous 30 days",
  "Older",
] as const;
type GroupName = (typeof GROUP_ORDER)[number];

export function History() {
  const { items, error, removeLocally } = useInvoices();
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 180);

  const onDelete = async (id: string) => {
    if (!confirm("Delete this invoice? This cannot be undone.")) return;
    try {
      await api.deleteInvoice(id);
      removeLocally(id);
      toast.success("Invoice deleted.");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Couldn't delete.");
    }
  };

  const filtered = useMemo(() => {
    if (!items) return null;
    const q = debouncedQuery.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) =>
      [it.supplier_name, it.invoice_number, it.currency, it.provider]
        .filter((v): v is string => typeof v === "string")
        .some((v) => v.toLowerCase().includes(q))
    );
  }, [items, debouncedQuery]);

  const grouped = useMemo(() => {
    if (!filtered) return null;
    const buckets = new Map<GroupName, InvoiceListItem[]>();
    const now = new Date();
    for (const it of filtered) {
      const key = groupFor(it.created_at, now);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key)!.push(it);
    }
    return GROUP_ORDER.flatMap((name) => {
      const rows = buckets.get(name);
      return rows && rows.length ? [{ name, rows }] : [];
    });
  }, [filtered]);

  const totalCount = items?.length ?? 0;
  const matchCount = filtered?.length ?? 0;
  const searching = debouncedQuery.trim().length > 0;

  return (
    <AppLayout>
      <div className="mx-auto max-w-6xl pt-6 sm:pt-10 animate-fade-in">
        <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-4xl sm:text-5xl">Your invoices</h1>
            <p className="mt-2 text-muted-foreground">
              A richer view of everything you've extracted. Click any card to open it.
            </p>
          </div>
        </header>

        <SearchBar
          query={query}
          onChange={setQuery}
          hint={
            items === null
              ? ""
              : searching
                ? `${matchCount} of ${totalCount}`
                : `${totalCount} total`
          }
        />

        {error && (
          <div className="mt-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {items === null && !error && <SkeletonGrid />}

        {items && items.length === 0 && (
          <Card className="mt-6">
            <CardHeader>
              <div className="mb-2 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                <FileText className="h-6 w-6" />
              </div>
              <CardTitle>No invoices yet</CardTitle>
              <CardDescription>Extract one and it will land here.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link to="/">Extract an invoice</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {items && items.length > 0 && filtered && filtered.length === 0 && (
          <div className="mt-6 rounded-2xl border border-border bg-card p-10 text-center shadow-soft">
            <div className="mx-auto mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <Search className="h-5 w-5" />
            </div>
            <p className="text-sm text-muted-foreground">
              No invoices match{" "}
              <span className="font-medium text-foreground">"{debouncedQuery}"</span>.
            </p>
          </div>
        )}

        {grouped && grouped.length > 0 && (
          <div className="mt-6 space-y-8">
            {grouped.map(({ name, rows }) => (
              <section key={name}>
                <h2 className="mb-3 flex items-baseline gap-2 px-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {name}
                  </span>
                  <span className="text-[11px] tabular-nums text-muted-foreground/60">
                    {rows.length}
                  </span>
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {rows.map((it, i) => (
                    <InvoiceCard
                      key={it.id}
                      item={it}
                      index={i}
                      onDelete={() => onDelete(it.id)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function SearchBar({
  query,
  onChange,
  hint,
}: {
  query: string;
  onChange: (v: string) => void;
  hint: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search supplier, invoice number, provider…"
          className="h-11 rounded-full pl-9 pr-10"
          autoComplete="off"
          spellCheck={false}
        />
        {query && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground ring-focus"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
      {hint && (
        <span className="hidden text-xs tabular-nums text-muted-foreground sm:inline">{hint}</span>
      )}
    </div>
  );
}

function InvoiceCard({
  item,
  index,
  onDelete,
}: {
  item: InvoiceListItem;
  index: number;
  onDelete: () => void;
}) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className="group relative overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-pop"
    >
      <Link
        to={`/invoice/${item.id}`}
        className="absolute inset-0 ring-focus"
        aria-label={`Open invoice ${item.invoice_number ?? ""} from ${item.supplier_name ?? "unknown supplier"}`}
      />

      {/* Letterbox preview */}
      <div className="relative aspect-[4/3] overflow-hidden bg-muted">
        <CardThumb id={item.id} mimeType={item.mime_type} />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/20 to-transparent" />
        <div className="absolute left-3 top-3 flex items-center gap-1.5">
          <Badge
            variant="secondary"
            className="bg-background/80 text-foreground text-[10px] backdrop-blur"
          >
            {item.provider}
          </Badge>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDelete();
          }}
          aria-label="Delete invoice"
          className="absolute right-3 bottom-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full bg-background/80 text-foreground/80 opacity-0 backdrop-blur transition-all hover:bg-destructive/90 hover:text-destructive-foreground focus-visible:opacity-100 group-hover:opacity-100 ring-focus"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="relative space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="min-w-0 font-display text-lg leading-tight text-balance">
            {item.supplier_name ?? "Untitled supplier"}
          </h3>
          {item.all_checks_pass ? (
            <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-label="All checks passed" />
          ) : (
            <XCircle className="h-4 w-4 shrink-0 text-destructive" aria-label="Some checks failed" />
          )}
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="truncate font-mono text-xs text-muted-foreground">
            {item.invoice_number ?? "no number"}
          </span>
          <span className="font-mono text-base font-semibold tabular-nums text-foreground">
            {formatCurrency(item.total_amount, item.currency ?? "NPR")}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
          <span>{formatDate(item.invoice_date)}</span>
          <span>{relativeTime(item.created_at)}</span>
        </div>
      </div>
    </motion.article>
  );
}

function CardThumb({ id, mimeType }: { id: string; mimeType: string }) {
  const isPdf = mimeType === "application/pdf";
  const [failed, setFailed] = useState(false);

  if (isPdf) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 bg-destructive/5 text-destructive">
        <FileText className="h-10 w-10" strokeWidth={1.2} />
        <span className="text-[10px] font-bold tracking-widest">PDF DOCUMENT</span>
      </div>
    );
  }
  if (failed) {
    return (
      <div className="flex h-full w-full items-center justify-center text-muted-foreground">
        <ImageIcon className="h-8 w-8" strokeWidth={1.2} />
      </div>
    );
  }
  return (
    <img
      src={api.imageUrl(id)}
      alt=""
      loading="lazy"
      decoding="async"
      className={cn(
        "h-full w-full object-cover transition-transform duration-500",
        "group-hover:scale-[1.03]"
      )}
      onError={() => setFailed(true)}
    />
  );
}

function SkeletonGrid() {
  return (
    <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft"
        >
          <div className="aspect-[4/3] animate-pulse-soft bg-muted" />
          <div className="space-y-2 p-4">
            <div className="h-4 w-3/4 animate-pulse-soft rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse-soft rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}

// --------- date / due helpers ----------

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function groupFor(iso: string, now: Date): GroupName {
  const created = new Date(iso);
  if (Number.isNaN(created.valueOf())) return "Older";
  const today = startOfDay(now);
  const days = Math.floor((today.valueOf() - startOfDay(created).valueOf()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Previous 7 days";
  if (days < 30) return "Previous 30 days";
  return "Older";
}


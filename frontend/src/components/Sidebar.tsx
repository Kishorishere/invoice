import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ChevronRight,
  FileText,
  Gauge,
  History as HistoryIcon,
  Image as ImageIcon,
  LayoutGrid,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Users as UsersIcon,
  X,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useDebouncedValue } from "@/lib/hooks";
import { useInvoices } from "@/lib/invoicesContext";
import type { InvoiceListItem } from "@/lib/types";
import { cn, formatCurrency, formatDate } from "@/lib/utils";

const RECENT_LIMIT = 6;
const COLLAPSED_KEY = "invoice.ai:sidebar-collapsed";
const EXPANDED_W = 320; // px — matches the previous w-80
const COLLAPSED_W = 64;

export function Sidebar() {
  const { isAdmin } = useAuth();
  const { items, loading } = useInvoices();
  const [q, setQ] = useState("");
  const debouncedQ = useDebouncedValue(q, 150);

  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  });

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  const visible = useMemo(() => {
    if (!items) return null;
    const needle = debouncedQ.trim().toLowerCase();
    const base = needle
      ? items.filter((it) =>
          [it.supplier_name, it.invoice_number, it.currency, it.provider]
            .filter((v): v is string => typeof v === "string")
            .some((v) => v.toLowerCase().includes(needle))
        )
      : items;
    return needle ? base : base.slice(0, RECENT_LIMIT);
  }, [items, debouncedQ]);

  return (
    <aside
      className="relative h-dvh shrink-0 overflow-hidden border-r border-border bg-card transition-[width] duration-300 ease-out will-change-[width]"
      style={{ width: collapsed ? COLLAPSED_W : EXPANDED_W }}
      aria-label="Sidebar"
    >
      {/* Expanded layer — always rendered at full width; fades when collapsed.
          Keeping its layout fixed is what makes the width transition jitter-free:
          the parent just clips the right edge, no child reflow happens. */}
      <div
        className="absolute inset-y-0 left-0 flex flex-col transition-opacity duration-200 ease-out"
        style={{
          width: EXPANDED_W,
          opacity: collapsed ? 0 : 1,
          pointerEvents: collapsed ? "none" : "auto",
        }}
        aria-hidden={collapsed}
      >
        <div className="flex h-16 shrink-0 items-center justify-between gap-2 px-6">
          <Link to="/" className="flex items-center gap-2 group">
            <img
              src="/invoice-icon.png"
              alt=""
              aria-hidden="true"
              className="h-7 w-7 object-contain dark:invert"
            />
            <span className="font-display text-xl leading-none">invoice.ai</span>
          </Link>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ring-focus"
            aria-label="Collapse sidebar"
            title="Collapse"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        </div>

        <div className="border-t border-border" />

        <nav className="flex flex-col gap-1 px-4 py-4">
          <SidebarPill to="/" icon={<LayoutGrid className="h-4 w-4" />}>
            Extract Invoice
          </SidebarPill>
          {isAdmin && (
            <SidebarPill to="/admin/users" icon={<UsersIcon className="h-4 w-4" />}>
              Users
            </SidebarPill>
          )}
          {isAdmin && (
            <SidebarPill to="/admin/limits" icon={<Gauge className="h-4 w-4" />}>
              Limits
            </SidebarPill>
          )}
        </nav>

        <div className="flex items-center justify-between px-6 pb-2 pt-4">
          <h3 className="text-sm font-medium text-foreground">Recent Invoices</h3>
          <Link
            to="/history"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground ring-focus rounded-md px-1"
          >
            View all <ChevronRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="px-4 pb-3">
          <SearchInput value={q} onChange={setQ} />
        </div>

        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {loading && items === null && <SidebarSkeleton />}
          {items && visible?.length === 0 && (
            <EmptyBlurb search={debouncedQ.trim().length > 0} />
          )}
          {visible && visible.length > 0 && (
            <ul className="space-y-2">
              {visible.map((it, i) => (
                <SidebarInvoiceRow key={it.id} item={it} index={i} />
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Collapsed strip — icon-only. Rendered on top; fades in when collapsed.
          Fixed width means its own layout never reflows, so the fade is clean. */}
      <div
        className="absolute inset-y-0 left-0 flex flex-col items-center gap-1 py-4 transition-opacity duration-200 ease-out"
        style={{
          width: COLLAPSED_W,
          opacity: collapsed ? 1 : 0,
          pointerEvents: collapsed ? "auto" : "none",
        }}
        aria-hidden={!collapsed}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ring-focus"
          aria-label="Expand sidebar"
          title="Expand"
        >
          <PanelLeftOpen className="h-4 w-4" />
        </button>

        <IconOnlyLink to="/" icon={<LayoutGrid className="h-4 w-4" />} label="Extract Invoice" />
        {isAdmin && (
          <IconOnlyLink
            to="/admin/users"
            icon={<UsersIcon className="h-4 w-4" />}
            label="Users"
          />
        )}
        {isAdmin && (
          <IconOnlyLink
            to="/admin/limits"
            icon={<Gauge className="h-4 w-4" />}
            label="Limits"
          />
        )}

        <div className="my-2 h-px w-8 bg-border" />

        <IconOnlyLink
          to="/history"
          icon={<HistoryIcon className="h-4 w-4" />}
          label="History"
        />
      </div>
    </aside>
  );
}

function IconOnlyLink({
  to,
  icon,
  label,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      title={label}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          "inline-flex h-9 w-9 items-center justify-center rounded-xl transition-colors ring-focus",
          isActive
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        )
      }
    >
      {icon}
    </NavLink>
  );
}

function SidebarPill({
  to,
  icon,
  children,
}: {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ring-focus",
          isActive
            ? "bg-muted text-foreground"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        )
      }
    >
      {icon}
      {children}
    </NavLink>
  );
}

function SearchInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search invoices..."
        autoComplete="off"
        spellCheck={false}
        className="h-10 w-full rounded-full border border-border bg-muted/50 pl-9 pr-9 text-sm placeholder:text-muted-foreground outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear"
          className="absolute right-2 top-1/2 inline-flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

function SidebarInvoiceRow({ item, index }: { item: InvoiceListItem; index: number }) {
  const { pathname } = useLocation();
  const active = pathname === `/invoice/${item.id}`;
  return (
    <motion.li
      initial={{ opacity: 0, y: 2 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02 }}
    >
      <Link
        to={`/invoice/${item.id}`}
        className={cn(
          "group flex items-center gap-3 rounded-xl border p-2 text-left transition-all ring-focus",
          active
            ? "border-border bg-muted/50"
            : "border-transparent hover:border-border hover:bg-muted/40"
        )}
      >
        <SidebarThumb id={item.id} mimeType={item.mime_type} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] font-semibold uppercase tracking-wide text-foreground">
            {item.supplier_name ?? "Untitled supplier"}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            <span className="font-mono">{item.invoice_number ?? "—"}</span>
            {item.invoice_date && (
              <>
                {" · "}
                {formatDate(item.invoice_date)}
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[11px] tabular-nums text-foreground">
            {formatCurrency(item.total_amount, item.currency ?? "NPR")}
          </span>
          <ChevronRight className="h-3 w-3 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>
      </Link>
    </motion.li>
  );
}

function SidebarThumb({ id, mimeType }: { id: string; mimeType: string }) {
  const isPdf = mimeType === "application/pdf";
  const [failed, setFailed] = useState(false);

  if (isPdf) {
    return (
      <div className="flex h-11 w-11 shrink-0 flex-col items-center justify-center overflow-hidden rounded-lg border border-destructive/20 bg-destructive/10 text-destructive">
        <FileText className="h-4 w-4" />
        <span className="text-[7px] font-bold tracking-wider">PDF</span>
      </div>
    );
  }
  if (failed) {
    return (
      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
        <ImageIcon className="h-3.5 w-3.5" />
      </div>
    );
  }
  return (
    <div className="h-11 w-11 shrink-0 overflow-hidden rounded-lg border border-border bg-muted">
      <img
        src={api.imageUrl(id)}
        alt=""
        loading="lazy"
        decoding="async"
        className="h-full w-full object-cover"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

function SidebarSkeleton() {
  return (
    <ul className="space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <li
          key={i}
          className="flex items-center gap-3 rounded-xl border border-transparent p-2"
        >
          <div className="h-11 w-11 shrink-0 animate-pulse-soft rounded-lg bg-muted" />
          <div className="flex-1 space-y-1.5">
            <div className="h-2.5 w-28 animate-pulse-soft rounded bg-muted" />
            <div className="h-2 w-20 animate-pulse-soft rounded bg-muted" />
          </div>
          <div className="h-2.5 w-14 animate-pulse-soft rounded bg-muted" />
        </li>
      ))}
    </ul>
  );
}

function EmptyBlurb({ search }: { search: boolean }) {
  return (
    <div className="rounded-xl border border-dashed border-border px-4 py-6 text-center">
      <p className="text-xs text-muted-foreground text-balance">
        {search
          ? "No invoices match that search."
          : "Nothing here yet. Your extracted invoices will appear in this list."}
      </p>
    </div>
  );
}

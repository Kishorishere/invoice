import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "./api";
import type { InvoiceListItem } from "./types";
import { useAuth } from "./auth";

interface InvoicesCtx {
  items: InvoiceListItem[] | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /** Optimistically remove an item (used after DELETE success). */
  removeLocally: (id: string) => void;
  /** Insert at the top (used after POST /extract success). */
  prepend: (item: InvoiceListItem) => void;
}

const InvoicesContext = createContext<InvoicesCtx | undefined>(undefined);

export function InvoicesProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [items, setItems] = useState<InvoiceListItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      setItems(await api.listInvoices());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load invoices.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) void refresh();
    else setItems(null);
  }, [user, refresh]);

  const removeLocally = useCallback((id: string) => {
    setItems((cur) => (cur ? cur.filter((i) => i.id !== id) : cur));
  }, []);

  const prepend = useCallback((item: InvoiceListItem) => {
    setItems((cur) => (cur ? [item, ...cur.filter((i) => i.id !== item.id)] : [item]));
  }, []);

  const value = useMemo(
    () => ({ items, loading, error, refresh, removeLocally, prepend }),
    [items, loading, error, refresh, removeLocally, prepend]
  );

  return <InvoicesContext.Provider value={value}>{children}</InvoicesContext.Provider>;
}

export function useInvoices(): InvoicesCtx {
  const ctx = useContext(InvoicesContext);
  if (!ctx) throw new Error("useInvoices must be used inside <InvoicesProvider>");
  return ctx;
}

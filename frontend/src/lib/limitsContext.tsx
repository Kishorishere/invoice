import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, api } from "./api";
import { useAuth } from "./auth";
import type { LimitsStatus } from "./types";

interface LimitsCtx {
  status: LimitsStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const LimitsContext = createContext<LimitsCtx | undefined>(undefined);

export function LimitsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [status, setStatus] = useState<LimitsStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      setStatus(await api.getLimits());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load limits.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) void refresh();
    else setStatus(null);
  }, [user, refresh]);

  const value = useMemo(
    () => ({ status, loading, error, refresh }),
    [status, loading, error, refresh]
  );

  return <LimitsContext.Provider value={value}>{children}</LimitsContext.Provider>;
}

export function useLimits(): LimitsCtx {
  const ctx = useContext(LimitsContext);
  if (!ctx) throw new Error("useLimits must be used inside <LimitsProvider>");
  return ctx;
}

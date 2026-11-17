// Client-side cache for /providers/{name}/models so the dropdown opens
// instantly after the first fetch. Scope: this browser tab's lifetime.
// Backend also caches heavily (24h in-memory), so a tab reload still won't
// hit upstream — this is the second level.

import { api } from "./api";
import type { ModelsResponse } from "./types";

type State =
  | { kind: "idle" }
  | { kind: "loading"; promise: Promise<ModelsResponse> }
  | { kind: "ok"; value: ModelsResponse; at: number }
  | { kind: "err"; error: Error; at: number };

const cache = new Map<string, State>();
const FRESH_MS = 60 * 60 * 1000; // 1h — forget errors sooner than that too

export function getCached(provider: string): ModelsResponse | null {
  const s = cache.get(provider);
  if (s?.kind === "ok" && Date.now() - s.at < FRESH_MS) return s.value;
  return null;
}

export async function fetchModels(provider: string): Promise<ModelsResponse> {
  const existing = cache.get(provider);
  if (existing?.kind === "ok" && Date.now() - existing.at < FRESH_MS) {
    return existing.value;
  }
  if (existing?.kind === "loading") return existing.promise;

  const promise = api
    .providerModels(provider)
    .then((value) => {
      cache.set(provider, { kind: "ok", value, at: Date.now() });
      return value;
    })
    .catch((error: Error) => {
      cache.set(provider, { kind: "err", error, at: Date.now() });
      throw error;
    });

  cache.set(provider, { kind: "loading", promise });
  return promise;
}

export function invalidate(provider?: string) {
  if (provider) cache.delete(provider);
  else cache.clear();
}

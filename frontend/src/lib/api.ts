import type {
  AdminUserRow,
  ExportFormat,
  ExtractResponse,
  InvoiceListItem,
  LimitsConfig,
  LimitsStatus,
  ModelsResponse,
  ProvidersInfo,
  Role,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown; // raw JSON body when the error payload is structured (e.g. 429 quota)
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.name = "ApiError";
  }
}

const CSRF_COOKIE = "ix_csrf";
const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | null {
  // document.cookie is a ; -separated string of "name=value" pairs.
  const prefix = name + "=";
  for (const chunk of document.cookie.split(";")) {
    const trimmed = chunk.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { parseJson = true }: { parseJson?: boolean } = {}
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const method = (init.method ?? "GET").toUpperCase();
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers.set(CSRF_HEADER, csrf);
    // If there's no CSRF cookie, we still send the request and let the
    // server 403 — avoids silently eating the user's action.
  }

  const resp = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include", // cookies ride on every request
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    let raw: unknown = undefined;
    try {
      const body = await resp.json();
      raw = body?.detail;
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) {
        detail = body.detail
          .map((d: { msg?: string }) => d?.msg ?? "")
          .filter(Boolean)
          .join(", ");
      } else if (body?.detail && typeof body.detail === "object" && typeof body.detail.message === "string") {
        detail = body.detail.message;
      }
    } catch {
      /* body wasn't JSON; keep statusText */
    }
    throw new ApiError(resp.status, detail || `Request failed (${resp.status})`, raw);
  }

  if (!parseJson || resp.status === 204) {
    return undefined as T;
  }
  return (await resp.json()) as T;
}

// ---------- Auth ----------
interface AuthResponse {
  user: User;
}

export const api = {
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>("/auth/me"),
  logout: () => request<void>("/auth/logout", { method: "POST" }, { parseJson: false }),

  providers: () => request<ProvidersInfo>("/providers"),
  providerModels: (provider: string) =>
    request<ModelsResponse>(`/providers/${encodeURIComponent(provider)}/models`),

  extract: (
    file: File,
    model?: string | null,
    options?: { force?: boolean }
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    if (model) fd.append("model", model);
    if (options?.force) fd.append("force", "true");
    return request<ExtractResponse>("/extract", { method: "POST", body: fd });
  },

  listInvoices: () => request<InvoiceListItem[]>("/invoices"),
  getInvoice: (id: string) => request<ExtractResponse>(`/invoices/${id}`),
  deleteInvoice: (id: string) =>
    request<void>(`/invoices/${id}`, { method: "DELETE" }, { parseJson: false }),
  imageUrl: (id: string) => `/api/invoices/${id}/image`,
  exportUrl: (id: string, format: ExportFormat) =>
    `/api/invoices/${id}/export?format=${format}`,

  // ---------- Admin ----------
  listUsers: () => request<AdminUserRow[]>("/admin/users"),
  createUser: (body: { email: string; password: string; role: Role }) =>
    request<User>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: string, body: { email?: string; role?: Role }) =>
    request<User>(`/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  resetUserPassword: (id: string, password: string) =>
    request<void>(
      `/admin/users/${id}/reset-password`,
      { method: "POST", body: JSON.stringify({ password }) },
      { parseJson: false }
    ),
  deleteUser: (id: string) =>
    request<void>(`/admin/users/${id}`, { method: "DELETE" }, { parseJson: false }),

  // ---------- Limits (self) ----------
  getLimits: () => request<LimitsStatus>("/limits"),

  // ---------- Admin: limits ----------
  getAdminLimits: () => request<LimitsConfig>("/admin/limits"),
  setAdminLimits: (patch: Partial<LimitsConfig>) =>
    request<LimitsConfig>("/admin/limits", { method: "PUT", body: JSON.stringify(patch) }),
};

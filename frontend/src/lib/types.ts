// Mirrors backend/app/schemas.py. Keep in sync.

export type Role = "user" | "admin";

export interface User {
  id: string;
  email: string;
  role: Role;
  created_at: string;
}

export interface AdminUserRow {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  invoice_count: number;
}

export interface Party {
  name: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
}

export interface InvoiceItem {
  description: string;
  quantity: string;
  unit_price: number;
  total: number;
}

export interface InvoiceData {
  invoice_number: string;
  invoice_date: string | null;
  due_date: string | null;
  payment_terms: string | null;
  supplier: Party;
  bill_to: Party;
  items: InvoiceItem[];
  subtotal: number | null;
  vat_rate: number | null;
  vat_amount: number | null;
  total: number;
  currency: string;
  notes: string[];
}

export type CheckStatus = "pass" | "fail" | "skipped";

export interface ValidationCheck {
  name: string;
  status: CheckStatus;
  message: string;
  delta: number | null;
}

export interface ValidationResult {
  checks: ValidationCheck[];
  all_pass: boolean;
}

export interface ExtractResponse {
  invoice_id: string;
  provider: string;
  model: string | null;
  data: InvoiceData;
  validation: ValidationResult;
  created_at: string;
}

export interface InvoiceListItem {
  id: string;
  provider: string;
  model: string | null;
  invoice_number: string | null;
  supplier_name: string | null;
  total_amount: number | null;
  currency: string | null;
  invoice_date: string | null;
  due_date: string | null;
  all_checks_pass: boolean;
  created_at: string;
  mime_type: string;
}

export interface ProvidersInfo {
  available: string[];
  default: string | null;
}

export interface ModelInfo {
  id: string;
  label: string;
}

export interface ModelsResponse {
  provider: string;
  default: string | null;
  models: ModelInfo[];
  cached: boolean;
}

export type ExportFormat = "json" | "csv" | "ubl" | "facturx";

export interface LimitsConfig {
  max_files_per_upload: number;
  max_per_hour: number;
  max_per_day: number;
  max_per_month: number;
}

export interface WindowCounts {
  hour: number;
  day: number;
  month: number;
}

export interface WindowResets {
  hour: string;
  day: string;
  month: string;
}

export interface LimitsStatus {
  limits: LimitsConfig;
  usage: WindowCounts;
  remaining: WindowCounts;
  reset_at: WindowResets;
}

export type QuotaScope = "hour" | "day" | "month";

export interface QuotaExceededDetail {
  message: string;
  scope: QuotaScope;
  limit: number;
  used: number;
  retry_after_seconds: number;
  reset_at: string;
  remaining: WindowCounts;
}

export interface DuplicateDetail {
  message: string;
  duplicate_of: string;
  uploaded_at: string; // ISO
  invoice_number: string | null;
  supplier_name: string | null;
  total_amount: number | null;
  currency: string | null;
  all_checks_pass: boolean;
}

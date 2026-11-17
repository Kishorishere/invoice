import { useState } from "react";
import { Download, Image as ImageIcon } from "lucide-react";

import { CopyField } from "@/components/CopyField";
import { ImageViewer } from "@/components/ImageViewer";
import { ValidationBadge } from "@/components/ValidationBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import type { ExtractResponse } from "@/lib/types";
import { formatCurrency, formatDate } from "@/lib/utils";

interface Props {
  response: ExtractResponse;
  imageSrc?: string | null;
}

export function InvoiceResults({ response, imageSrc }: Props) {
  const { data, validation } = response;
  const currency = data.currency || "NPR";
  const [viewerOpen, setViewerOpen] = useState(false);

  return (
    <div>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight text-balance">
            {data.supplier.name ?? "Untitled supplier"}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Invoice {data.invoice_number}
          </p>
        </div>
        <div className="flex items-start gap-5">
          <div className="text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Total
            </p>
            <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums">
              {formatCurrency(data.total, currency)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Extracted
            </p>
            <p className="mt-0.5 text-sm">{formatDate(response.created_at)}</p>
          </div>
          <ExportMenu invoiceId={response.invoice_id} />
        </div>
      </header>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* Image preview — left */}
        <aside className="lg:col-span-2">
          <div className="sticky top-2 overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
            {imageSrc ? (
              <button
                type="button"
                onClick={() => setViewerOpen(true)}
                className="block w-full cursor-zoom-in ring-focus"
                aria-label="Open invoice image"
              >
                <img src={imageSrc} alt="Invoice" className="w-full object-contain" />
              </button>
            ) : (
              <div className="flex aspect-[3/4] items-center justify-center bg-muted/50 text-muted-foreground">
                <ImageIcon className="h-8 w-8" />
              </div>
            )}
            <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-2.5 text-xs text-muted-foreground">
              <span>Source</span>
              <Badge variant="secondary" className="font-mono text-[11px]">
                {response.model ?? response.provider}
              </Badge>
            </div>
          </div>
        </aside>

        {/* Extracted fields — right */}
        <section className="space-y-5 lg:col-span-3">

        {validation.checks.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {validation.checks.map((c) => (
              <ValidationBadge key={c.name} check={c} />
            ))}
          </div>
        )}

        <div className="rounded-2xl border border-border bg-card p-3 shadow-soft">
          <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
            <CopyField label="Invoice number" value={data.invoice_number} mono />
            <CopyField label="Invoice date" value={formatDate(data.invoice_date)} />
            <CopyField label="Due date" value={formatDate(data.due_date)} />
            {data.payment_terms && (
              <CopyField label="Payment terms" value={data.payment_terms} />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <PartyCard title="Supplier" party={data.supplier} />
          <PartyCard title="Bill to" party={data.bill_to} />
        </div>

        <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-soft">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="text-sm font-semibold">Line items</h3>
            <Badge variant="secondary">{data.items.length}</Badge>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                <tr className="border-b border-border">
                  <th className="px-4 py-2.5 text-left font-medium">#</th>
                  <th className="px-4 py-2.5 text-left font-medium">Description</th>
                  <th className="px-4 py-2.5 text-left font-medium">Qty</th>
                  <th className="px-4 py-2.5 text-right font-medium">Unit price</th>
                  <th className="px-4 py-2.5 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">
                      No line items extracted.
                    </td>
                  </tr>
                )}
                {data.items.map((item, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/70 last:border-0 transition-colors hover:bg-muted/40"
                  >
                    <td className="px-4 py-3 text-muted-foreground">{i + 1}</td>
                    <td className="px-4 py-3 font-medium">{item.description}</td>
                    <td className="px-4 py-3 text-muted-foreground">{item.quantity}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">
                      {formatCurrency(item.unit_price, currency)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">
                      {formatCurrency(item.total, currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="text-sm">
                <tr>
                  <td colSpan={3} />
                  <td className="px-4 py-2 text-right text-muted-foreground">Subtotal</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {formatCurrency(data.subtotal, currency)}
                  </td>
                </tr>
                {data.vat_amount != null && (
                  <tr>
                    <td colSpan={3} />
                    <td className="px-4 py-2 text-right text-muted-foreground">
                      VAT{data.vat_rate != null ? ` (${data.vat_rate}%)` : ""}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums">
                      {formatCurrency(data.vat_amount, currency)}
                    </td>
                  </tr>
                )}
                <tr className="border-t border-border">
                  <td colSpan={3} />
                  <td className="px-4 py-3 text-right text-sm font-semibold">Total</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums text-base font-semibold">
                    {formatCurrency(data.total, currency)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        {data.notes.length > 0 && (
          <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <h3 className="text-sm font-semibold">Notes</h3>
            <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
              {data.notes.map((n, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-primary">•</span>
                  <span>{n}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        </section>
      </div>

      {imageSrc && (
        <ImageViewer open={viewerOpen} onOpenChange={setViewerOpen} src={imageSrc} />
      )}
    </div>
  );
}

function PartyCard({ title, party }: { title: string; party: ExtractResponse["data"]["supplier"] }) {
  const empty = !party.name && !party.address && !party.email && !party.phone;
  return (
    <div className="rounded-2xl border border-border bg-card p-3 shadow-soft">
      <p className="px-3 pt-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {empty ? (
        <p className="px-3 py-3 text-sm text-muted-foreground">Not extracted.</p>
      ) : (
        <>
          <CopyField label="Name" value={party.name} />
          <CopyField label="Address" value={party.address} />
          <CopyField label="Email" value={party.email} />
          <CopyField label="Phone" value={party.phone} />
        </>
      )}
    </div>
  );
}

function ExportMenu({ invoiceId }: { invoiceId: string }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          <Download className="h-4 w-4" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[14rem]">
        <DropdownMenuLabel>Download as</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <a href={api.exportUrl(invoiceId, "json")}>
            <span className="font-mono text-xs text-muted-foreground">.json</span>
            Structured JSON
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={api.exportUrl(invoiceId, "csv")}>
            <span className="font-mono text-xs text-muted-foreground">.csv</span>
            Spreadsheet (CSV)
          </a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-[10px]">E-invoicing</DropdownMenuLabel>
        <DropdownMenuItem asChild>
          <a href={api.exportUrl(invoiceId, "ubl")}>
            <span className="font-mono text-xs text-muted-foreground">.xml</span>
            UBL 2.1
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={api.exportUrl(invoiceId, "facturx")}>
            <span className="font-mono text-xs text-muted-foreground">.xml</span>
            Factur-X / ZUGFeRD
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

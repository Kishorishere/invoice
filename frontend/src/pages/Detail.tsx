import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { AppLayout } from "@/components/AppLayout";
import { InvoiceResults } from "@/components/InvoiceResults";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { ExtractResponse } from "@/lib/types";

export function Detail() {
  const { id = "" } = useParams();
  const [resp, setResp] = useState<ExtractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setResp(null);
    setError(null);
    api
      .getInvoice(id)
      .then(setResp)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Couldn't load invoice.")
      );
  }, [id]);

  return (
    <AppLayout
      rightTop={
        <Button asChild variant="outline" size="sm" className="h-7 gap-1.5 rounded-full px-3 text-xs">
          <Link to="/history">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Link>
        </Button>
      }
    >
      <div className="mx-auto w-full max-w-screen-2xl pt-2 animate-fade-in">
        {error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {!resp && !error && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
            <div className="aspect-[3/4] animate-pulse-soft rounded-2xl bg-muted lg:col-span-2" />
            <div className="space-y-4 lg:col-span-3">
              <div className="h-20 animate-pulse-soft rounded-2xl bg-muted" />
              <div className="h-40 animate-pulse-soft rounded-2xl bg-muted" />
              <div className="h-64 animate-pulse-soft rounded-2xl bg-muted" />
            </div>
          </div>
        )}

        {resp && <InvoiceResults response={resp} imageSrc={api.imageUrl(resp.invoice_id)} />}
      </div>
    </AppLayout>
  );
}

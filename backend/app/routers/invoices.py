"""List / fetch / delete / export persisted invoices for the current user."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.config import get_settings
from app.deps import CsrfProtected, CurrentUser, DbSession
from app.models import Invoice
from app.rate_limit import limiter
from app.schemas import ExtractResponse, InvoiceData, InvoiceListItem, ValidationResult
from app.services.exporters import to_csv_bytes, to_facturx_xml_bytes, to_json_bytes, to_ubl_bytes

router = APIRouter(prefix="/invoices", tags=["invoices"])

_settings = get_settings()


@router.get("", response_model=list[InvoiceListItem])
@limiter.limit(_settings.rate_limit_invoices_read)
def list_invoices(
    request: Request, user: CurrentUser, session: DbSession
) -> list[InvoiceListItem]:
    rows = session.exec(
        select(Invoice).where(Invoice.user_id == user.id).order_by(Invoice.created_at.desc())
    ).all()
    return [
        InvoiceListItem(
            id=r.id,
            provider=r.provider,
            model=r.model,
            invoice_number=r.invoice_number,
            supplier_name=r.supplier_name,
            total_amount=r.total_amount,
            currency=r.currency,
            invoice_date=r.invoice_date,
            due_date=r.due_date,
            all_checks_pass=r.all_checks_pass,
            created_at=r.created_at,
            mime_type=r.mime_type,
        )
        for r in rows
    ]


@router.get("/{invoice_id}", response_model=ExtractResponse)
@limiter.limit(_settings.rate_limit_invoices_read)
def get_invoice(
    request: Request, invoice_id: str, user: CurrentUser, session: DbSession
) -> ExtractResponse:
    row = _owned(session, invoice_id, user.id)
    return ExtractResponse(
        invoice_id=row.id,
        provider=row.provider,
        model=row.model,
        data=InvoiceData.model_validate(json.loads(row.data_json)),
        validation=ValidationResult.model_validate(json.loads(row.validation_json)),
        created_at=row.created_at,
    )


@router.get("/{invoice_id}/image")
@limiter.limit(_settings.rate_limit_invoices_read)
def get_invoice_image(
    request: Request, invoice_id: str, user: CurrentUser, session: DbSession
) -> FileResponse:
    """Serve the original upload. Invoice IDs are UUIDs and the bytes behind
    them never change, so we send strong immutable cache headers — the browser
    will reuse this across every <img src>, list row, and detail page without
    another round-trip. `private` keeps shared caches (CDNs, corporate proxies)
    from storing per-user content."""
    row = _owned(session, invoice_id, user.id)
    path = Path(get_settings().upload_dir) / row.file_path
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Original file is no longer on disk.")
    return FileResponse(
        path,
        media_type=row.mime_type,
        filename=row.file_name,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


ExportFormat = Literal["json", "csv", "ubl", "facturx"]


@router.get("/{invoice_id}/export")
@limiter.limit(_settings.rate_limit_invoices_read)
def export_invoice(
    request: Request,
    invoice_id: str,
    user: CurrentUser,
    session: DbSession,
    format: ExportFormat = "json",
) -> Response:
    row = _owned(session, invoice_id, user.id)
    inv = InvoiceData.model_validate(json.loads(row.data_json))
    base = (row.invoice_number or row.id).replace("/", "-")

    if format == "json":
        return Response(
            to_json_bytes(inv),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{base}.json"'},
        )
    if format == "csv":
        return Response(
            to_csv_bytes(inv),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{base}.csv"'},
        )
    if format == "ubl":
        return Response(
            to_ubl_bytes(inv),
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{base}.ubl.xml"'},
        )
    if format == "facturx":
        return Response(
            to_facturx_xml_bytes(inv),
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="{base}.facturx.xml"'},
        )
    # unreachable due to Literal typing, but keeps mypy honest
    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown format '{format}'.")


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(_settings.rate_limit_invoices_write)
def delete_invoice(
    request: Request,
    invoice_id: str,
    _csrf: CsrfProtected,
    user: CurrentUser,
    session: DbSession,
) -> None:
    row = _owned(session, invoice_id, user.id)
    path = Path(get_settings().upload_dir) / row.file_path
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass  # best effort; row deletion is the user-visible action
    session.delete(row)
    session.commit()


def _owned(session: Session, invoice_id: str, user_id: str) -> Invoice:
    row = session.get(Invoice, invoice_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found.")
    return row

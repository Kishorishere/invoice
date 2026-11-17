"""Per-user content-based dedupe.

Byte-exact only: we hash the raw upload bytes with SHA-256 and look for a
prior row from the same user with the same hash. Two phone photos of the
same paper invoice won't match — perceptual dedupe is a separate problem.

Trade-off: when a duplicate is found we return 409 WITHOUT ticking the
quota. The user hasn't actually consumed an extraction; charging them for
the server's "no" would feel punitive.
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Invoice
from app.schemas import DuplicateDetail


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_duplicate(session: Session, user_id: str, content_hash: str) -> Invoice | None:
    """Return the user's prior invoice with this content hash, if any."""
    stmt = (
        select(Invoice)
        .where(Invoice.user_id == user_id, Invoice.content_hash == content_hash)
        .order_by(Invoice.created_at.desc())
    )
    return session.exec(stmt).first()


def raise_duplicate(existing: Invoice) -> None:
    """Raise 409 with a DuplicateDetail body built from an existing row."""
    detail = DuplicateDetail(
        message=(
            "You've already extracted this invoice. Open the existing one, "
            "or extract again to overwrite the record."
        ),
        duplicate_of=existing.id,
        uploaded_at=existing.created_at,
        invoice_number=existing.invoice_number,
        supplier_name=existing.supplier_name,
        total_amount=existing.total_amount,
        currency=existing.currency,
        all_checks_pass=existing.all_checks_pass,
    )
    # FastAPI passes `detail` through json-encoding, which handles Decimal /
    # datetime naturally. Explicitly dump to a JSON-safe dict here so the
    # client parses it with no surprises.
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail.model_dump(mode="json"),
    )


__all__ = ["find_duplicate", "raise_duplicate", "sha256_hex"]

"""Business validation: arithmetic checks + due-date classification."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from app.schemas import InvoiceData, ValidationCheck, ValidationResult

# Allow 2 cents of slop — real invoices round line items independently.
MONEY_EPS = Decimal("0.02")
# Extra tolerance for VAT: subtotal * this, to allow for rounding on the rate.
VAT_RELATIVE_TOLERANCE = Decimal("0.0005")
_HUNDRED = Decimal("100")


def validate(inv: InvoiceData, *, today: date | None = None) -> ValidationResult:
    today = today or datetime.now(UTC).date()
    checks: list[ValidationCheck] = []

    checks.append(_check_required_fields(inv))
    checks.append(_check_items_present(inv))
    checks.append(_check_line_items(inv))
    checks.append(_check_subtotal(inv))
    checks.append(_check_vat(inv))
    checks.append(_check_total(inv))
    checks.append(_check_issue_date_not_future(inv, today))
    checks.append(_check_dates(inv))

    due_status, days = _due_status(inv, today)

    return ValidationResult(
        checks=checks,
        all_pass=all(c.status != "fail" for c in checks),
        due_status=due_status,
        days_until_due=days,
    )


def _check_required_fields(inv: InvoiceData) -> ValidationCheck:
    missing: list[str] = []
    if not (inv.invoice_number or "").strip():
        missing.append("invoice number")
    if not (inv.bill_to.name or "").strip():
        missing.append("bill-to")
    if missing:
        return ValidationCheck(
            name="required_fields",
            status="fail",
            message=f"Missing required field(s): {', '.join(missing)}.",
        )
    return ValidationCheck(
        name="required_fields",
        status="pass",
        message="Invoice number and bill-to both present.",
    )


_LEADING_NUMBER = re.compile(r"^\s*([+-]?\d+(?:[.,]\d+)?)")


def _parse_quantity(raw: str) -> Decimal | None:
    """Pull a leading number out of '50 pcs' / '10 hrs' / '2.5 kg'.

    Returns None for non-numeric quantities like '1 lot' when there's no
    unambiguous digit at the start — those rows are skipped silently.
    """
    match = _LEADING_NUMBER.match(raw or "")
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def _check_line_items(inv: InvoiceData) -> ValidationCheck:
    if not inv.items:
        return ValidationCheck(
            name="line_item_arithmetic",
            status="skipped",
            message="No line items to check.",
        )
    mismatches: list[str] = []
    checked = 0
    for idx, item in enumerate(inv.items, start=1):
        qty = _parse_quantity(item.quantity)
        if qty is None:
            continue
        checked += 1
        expected = qty * item.unit_price
        if abs(expected - item.total) > MONEY_EPS:
            mismatches.append(
                f"row {idx}: {qty:g}×{item.unit_price:,.2f} = {expected:,.2f}, "
                f"printed {item.total:,.2f}"
            )
    if checked == 0:
        return ValidationCheck(
            name="line_item_arithmetic",
            status="skipped",
            message="No rows had a numeric quantity to verify.",
        )
    if mismatches:
        return ValidationCheck(
            name="line_item_arithmetic",
            status="fail",
            message="Line total mismatch — " + "; ".join(mismatches) + ".",
        )
    return ValidationCheck(
        name="line_item_arithmetic",
        status="pass",
        message=f"All {checked} verifiable row(s): qty × unit price = line total.",
    )


def _check_issue_date_not_future(inv: InvoiceData, today: date) -> ValidationCheck:
    issued = _parse_iso(inv.invoice_date)
    if issued is None:
        if (inv.invoice_date or "").strip():
            return ValidationCheck(
                name="issue_date_not_future",
                status="skipped",
                message=f"Issue date '{inv.invoice_date}' is non-Gregorian; skipped.",
            )
        return ValidationCheck(
            name="issue_date_not_future",
            status="skipped",
            message="No issue date extracted.",
        )
    # Year far outside a plausible Gregorian window almost certainly means
    # a non-Gregorian calendar slipped through as ISO (e.g. Bikram Sambat
    # 2079-04-01). Skip rather than fail.
    if abs(issued.year - today.year) > 50:
        return ValidationCheck(
            name="issue_date_not_future",
            status="skipped",
            message=f"Issue date '{inv.invoice_date}' is not in the Gregorian calendar; skipped.",
        )
    if issued > today:
        return ValidationCheck(
            name="issue_date_not_future",
            status="fail",
            message=f"Issue date {issued.isoformat()} is in the future (today is {today.isoformat()}).",
        )
    return ValidationCheck(
        name="issue_date_not_future",
        status="pass",
        message=f"Issued {issued.isoformat()} (on or before today).",
    )


def _check_items_present(inv: InvoiceData) -> ValidationCheck:
    if not inv.items:
        return ValidationCheck(
            name="items_present",
            status="fail",
            message="No line items were extracted.",
        )
    return ValidationCheck(
        name="items_present",
        status="pass",
        message=f"{len(inv.items)} line item(s) extracted.",
    )


def _check_subtotal(inv: InvoiceData) -> ValidationCheck:
    if inv.subtotal is None:
        return ValidationCheck(
            name="subtotal_matches_items",
            status="skipped",
            message="No subtotal printed on invoice.",
        )
    if not inv.items:
        return ValidationCheck(
            name="subtotal_matches_items",
            status="skipped",
            message="No items to sum.",
        )
    computed: Decimal = sum((i.total for i in inv.items), Decimal(0))
    delta = computed - inv.subtotal
    if abs(delta) <= MONEY_EPS:
        return ValidationCheck(
            name="subtotal_matches_items",
            status="pass",
            message=f"Σ(items) = {computed:,.2f} matches subtotal.",
            delta=_round2(delta),
        )
    return ValidationCheck(
        name="subtotal_matches_items",
        status="fail",
        message=f"Σ(items) = {computed:,.2f}, subtotal printed as {inv.subtotal:,.2f}.",
        delta=_round2(delta),
    )


def _check_vat(inv: InvoiceData) -> ValidationCheck:
    if inv.vat_rate is None or inv.vat_amount is None or inv.subtotal is None:
        return ValidationCheck(
            name="vat_computed_correctly",
            status="skipped",
            message="No VAT line on invoice.",
        )
    expected = inv.subtotal * inv.vat_rate / _HUNDRED
    delta = expected - inv.vat_amount
    tolerance = max(MONEY_EPS, abs(inv.subtotal) * VAT_RELATIVE_TOLERANCE)
    if abs(delta) <= tolerance:
        return ValidationCheck(
            name="vat_computed_correctly",
            status="pass",
            message=f"VAT {inv.vat_rate:g}% of {inv.subtotal:,.2f} ≈ {expected:,.2f}.",
            delta=_round2(delta),
        )
    return ValidationCheck(
        name="vat_computed_correctly",
        status="fail",
        message=(
            f"VAT {inv.vat_rate:g}% of {inv.subtotal:,.2f} should be "
            f"{expected:,.2f}, printed as {inv.vat_amount:,.2f}."
        ),
        delta=_round2(delta),
    )


def _check_total(inv: InvoiceData) -> ValidationCheck:
    if inv.subtotal is None:
        return ValidationCheck(
            name="total_equals_subtotal_plus_vat",
            status="skipped",
            message="No subtotal to compare.",
        )
    expected = inv.subtotal + (inv.vat_amount or Decimal(0))
    delta = expected - inv.total
    if abs(delta) <= MONEY_EPS:
        return ValidationCheck(
            name="total_equals_subtotal_plus_vat",
            status="pass",
            message=f"Subtotal + VAT = {expected:,.2f} matches total.",
            delta=_round2(delta),
        )
    return ValidationCheck(
        name="total_equals_subtotal_plus_vat",
        status="fail",
        message=(
            f"Subtotal + VAT = {expected:,.2f}, total printed as {inv.total:,.2f}."
        ),
        delta=_round2(delta),
    )


def _check_dates(inv: InvoiceData) -> ValidationCheck:
    issued = _parse_iso(inv.invoice_date)
    due = _parse_iso(inv.due_date)
    if issued is None and due is None:
        return ValidationCheck(
            name="dates_sensible",
            status="skipped",
            message="No dates extracted.",
        )
    if issued is None or due is None:
        return ValidationCheck(
            name="dates_sensible",
            status="skipped",
            message="Only one of issue/due date extracted.",
        )
    if due < issued:
        return ValidationCheck(
            name="dates_sensible",
            status="fail",
            message=f"Due date {due.isoformat()} is before issue date {issued.isoformat()}.",
        )
    return ValidationCheck(
        name="dates_sensible",
        status="pass",
        message=f"Issued {issued.isoformat()}, due {due.isoformat()}.",
    )


DUE_SOON_DAYS = 14


def _due_status(
    inv: InvoiceData, today: date
) -> tuple[str, int | None]:
    due = _parse_iso(inv.due_date)
    if due is None:
        return "unknown", None
    days = (due - today).days
    if days < 0:
        return "overdue", days
    if days <= DUE_SOON_DAYS:
        return "due_soon", days
    return "due_later", days


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _round2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))

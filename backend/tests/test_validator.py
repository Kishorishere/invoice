from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.schemas import InvoiceData, InvoiceItem, Party
from app.services.validator import validate


def _rivertech() -> InvoiceData:
    return InvoiceData(
        invoice_number="RT-2024-1052",
        invoice_date="2024-10-14",
        due_date="2024-11-13",
        supplier=Party(name="Rivertech Supplies Ltd."),
        bill_to=Party(name="Deutschelink GmbH"),
        items=[
            InvoiceItem(description="HDPE Pipe 110mm", quantity="50 pcs", unit_price=1250.0, total=62500.0),
            InvoiceItem(description="HDPE Elbow 90° 110mm", quantity="20 pcs", unit_price=450.0, total=9000.0),
            InvoiceItem(description="HDPE Coupling 110mm", quantity="30 pcs", unit_price=300.0, total=9000.0),
            InvoiceItem(description="Welding Service", quantity="10 hrs", unit_price=1500.0, total=15000.0),
            InvoiceItem(description="Delivery Charge", quantity="1 lot", unit_price=5000.0, total=5000.0),
        ],
        subtotal=100500.0,
        vat_rate=13.0,
        vat_amount=13065.0,
        total=113565.0,
        currency="NPR",
    )


def test_happy_path_all_pass() -> None:
    result = validate(_rivertech(), today=date(2024, 11, 1))
    assert result.all_pass is True
    assert result.due_status == "due_soon"
    assert result.days_until_due == 12
    by_name = {c.name: c for c in result.checks}
    assert by_name["subtotal_matches_items"].status == "pass"
    assert by_name["vat_computed_correctly"].status == "pass"
    assert by_name["total_equals_subtotal_plus_vat"].status == "pass"


def test_subtotal_mismatch_flagged() -> None:
    inv = _rivertech()
    inv.subtotal = 99999.0
    result = validate(inv, today=date(2024, 11, 1))
    assert result.all_pass is False
    check = next(c for c in result.checks if c.name == "subtotal_matches_items")
    assert check.status == "fail"
    assert check.delta is not None


def test_vat_skipped_when_not_present() -> None:
    inv = _rivertech()
    inv.vat_rate = None
    inv.vat_amount = None
    inv.total = inv.subtotal or 0.0
    result = validate(inv, today=date(2024, 11, 1))
    vat = next(c for c in result.checks if c.name == "vat_computed_correctly")
    assert vat.status == "skipped"


def test_overdue_status() -> None:
    result = validate(_rivertech(), today=date(2025, 1, 1))
    assert result.due_status == "overdue"
    assert result.days_until_due is not None and result.days_until_due < 0


def test_due_later_status() -> None:
    inv = _rivertech()
    inv.due_date = "2025-06-01"
    result = validate(inv, today=date(2025, 1, 1))
    assert result.due_status == "due_later"


def test_dates_swapped_flagged() -> None:
    inv = _rivertech()
    inv.invoice_date = "2024-11-14"
    inv.due_date = "2024-10-13"
    result = validate(inv, today=date(2024, 11, 1))
    dates = next(c for c in result.checks if c.name == "dates_sensible")
    assert dates.status == "fail"


def test_empty_items_flagged() -> None:
    inv = _rivertech()
    inv.items = []
    result = validate(inv, today=date(2024, 11, 1))
    items_check = next(c for c in result.checks if c.name == "items_present")
    assert items_check.status == "fail"
    assert result.all_pass is False


def test_required_fields_missing_bill_to_flagged() -> None:
    inv = _rivertech()
    inv.bill_to = Party()
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "required_fields")
    assert check.status == "fail"
    assert "bill-to" in check.message
    assert result.all_pass is False


def test_required_fields_passes_without_supplier() -> None:
    # Supplier isn't mandatory — many freelance/sole-proprietor invoices
    # put the issuer name at the top with no explicit "From:" label and
    # the model may not always tag it as supplier. Don't fail those.
    inv = _rivertech()
    inv.supplier = Party()
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "required_fields")
    assert check.status == "pass"


def test_line_item_arithmetic_flags_bad_rows() -> None:
    inv = _rivertech()
    inv.items[1].total = Decimal("9500.00")  # 20 × 450 = 9000, printed 9500
    inv.items[2].total = Decimal("8000.00")  # 30 × 300 = 9000, printed 8000
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "line_item_arithmetic")
    assert check.status == "fail"
    assert "row 2" in check.message
    assert "row 3" in check.message


def test_line_item_arithmetic_skips_non_numeric_quantities() -> None:
    inv = _rivertech()
    # Only the "1 lot" row remains — its quantity "1 lot" has a leading digit
    # so it IS verified. Replace with a truly non-numeric quantity.
    inv.items = [
        InvoiceItem(description="Consulting", quantity="lot", unit_price=5000.0, total=5000.0),
    ]
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "line_item_arithmetic")
    assert check.status == "skipped"


def test_issue_date_in_future_flagged() -> None:
    inv = _rivertech()
    inv.invoice_date = "2024-12-01"
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "issue_date_not_future")
    assert check.status == "fail"
    assert result.all_pass is False


def test_issue_date_today_passes() -> None:
    inv = _rivertech()
    inv.invoice_date = "2024-11-01"
    result = validate(inv, today=date(2024, 11, 1))
    check = next(c for c in result.checks if c.name == "issue_date_not_future")
    assert check.status == "pass"

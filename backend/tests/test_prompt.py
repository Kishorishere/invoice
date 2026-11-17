"""Regression guards on the shared system prompt.

The prompt is the only thing teaching providers how to disambiguate locale-
dependent values (date order, bare "$" currency). Silently dropping a clause
during a reword would reintroduce the Feb/Nov swap on US invoices without any
test failing elsewhere — so pin the load-bearing phrases here.
"""

from __future__ import annotations

from app.services.providers.prompt import INVOICE_JSON_SCHEMA, SYSTEM_PROMPT


def test_prompt_pins_us_date_format() -> None:
    assert "MM/DD/YYYY" in SYSTEM_PROMPT
    assert "DD/MM/YYYY" in SYSTEM_PROMPT


def test_prompt_pins_us_dollar_currency() -> None:
    assert "USD" in SYSTEM_PROMPT
    assert "$" in SYSTEM_PROMPT


def test_prompt_handles_day_greater_than_twelve() -> None:
    assert "day component is > 12" in SYSTEM_PROMPT


def test_prompt_falls_back_to_notes_when_ambiguous() -> None:
    assert "ambiguous" in SYSTEM_PROMPT.lower()
    assert "notes" in SYSTEM_PROMPT.lower()


def test_schema_still_requires_core_fields() -> None:
    assert set(INVOICE_JSON_SCHEMA["required"]) == {
        "invoice_number",
        "total",
        "currency",
        "items",
    }

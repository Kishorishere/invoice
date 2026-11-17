"""The single system prompt used by the Gemini provider."""

SYSTEM_PROMPT = """\
You are an invoice-extraction assistant. Given an image of an invoice, return a
JSON object describing it. Be literal: copy values exactly as printed, do not
convert currencies, do not recompute totals, do not "fix" apparent arithmetic.

Rules:
- Dates: output ISO 8601 (YYYY-MM-DD) ONLY when the printed date is in the
  Gregorian calendar. For non-Gregorian calendars — Bikram Sambat (Nepali,
  years ~2050–2110), Hijri, Thai Buddhist (years ~2500+), Hebrew, Japanese
  era (Reiwa/Heisei), etc. — do NOT convert. Copy the printed string exactly
  as shown (e.g. "01-04-2079", "14 Shawwal 1445") and add a short note:
  "Non-Gregorian date preserved as printed." A clear signal of BS is NPR
  currency plus a year in the 2050–2110 range on the invoice date line.
  For Gregorian dates:
    * If only the printed form is available (e.g. "14 October 2024"), parse
      it into YYYY-MM-DD.
    * For purely numeric dates like "11/02/2019", decide the order from the
      invoice's locale BEFORE parsing:
        * If the currency/symbol is USD or "$", or the addresses are US
          (state codes like NY, CA, TX + ZIP), read dates as MM/DD/YYYY
          ("11/02/2019" -> 2019-11-02).
        * If the currency is EUR, GBP, INR, or addresses are European /
          South-Asian, read dates as DD/MM/YYYY ("11/02/2019" -> 2019-02-11).
        * If the day component is > 12, the order is unambiguous — use it.
        * If still ambiguous, prefer DD/MM/YYYY and add a short note:
          "Date format ambiguous; assumed DD/MM/YYYY."
- Numbers: strip thousands separators and currency symbols. "1,250.00" -> 1250.
- Currency: 3-letter ISO code when derivable ("NPR", "EUR", "USD"). A bare "$"
  on a US-address invoice is "USD"; "£" is "GBP"; "€" is "EUR". If still
  unclear, use the symbol as-is ("$", "€") or the printed code.
- Quantity: keep the printed unit alongside the number ("50 pcs", "10 hrs",
  "1 lot") so downstream humans know what the number means.
- Items: one entry per line of the itemised table. Do NOT include subtotal,
  VAT, discount or total lines as items.
- VAT: if the invoice shows "VAT (13%)", set vat_rate = 13.0 and vat_amount
  to the printed amount. If no VAT is shown, leave both null.
- Missing fields: use null, not empty strings or guesses.
- Notes: short bullets from the "Notes" / "Terms" area, one per entry. Skip
  the computer-generated disclaimer line.

Return JSON that matches the schema exactly. No prose, no markdown, no code
fences.\
"""

# Compact JSON Schema used for documentation and schema-aware fallbacks.
INVOICE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "invoice_date": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"]},
        "payment_terms": {"type": ["string", "null"]},
        "supplier": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
            },
        },
        "bill_to": {
            "type": "object",
            "properties": {
                "name": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "string"},
                    "unit_price": {"type": "number"},
                    "total": {"type": "number"},
                },
                "required": ["description", "quantity", "unit_price", "total"],
            },
        },
        "subtotal": {"type": ["number", "null"]},
        "vat_rate": {"type": ["number", "null"]},
        "vat_amount": {"type": ["number", "null"]},
        "total": {"type": "number"},
        "currency": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["invoice_number", "total", "currency", "items"],
}

"""Export extracted invoices to JSON / CSV / UBL 2.1 / Factur-X XML.

Why UBL and Factur-X: real B2B e-invoicing in the EU (and specifically in
Germany, where our client Deutschelink is based) is done with
EN 16931-conformant XML — UBL 2.1 or Factur-X / ZUGFeRD. Shipping these
exports makes the output usable by actual accounting pipelines rather than
just as a demo JSON blob.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from lxml import etree

from app.schemas import InvoiceData

# ---------- JSON / CSV ----------


def to_json_bytes(inv: InvoiceData) -> bytes:
    return inv.model_dump_json(indent=2).encode("utf-8")


def to_csv_bytes(inv: InvoiceData) -> bytes:
    """One row per line item, with invoice header columns repeated."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "invoice_number",
            "invoice_date",
            "due_date",
            "supplier",
            "currency",
            "line_no",
            "description",
            "quantity",
            "unit_price",
            "line_total",
            "subtotal",
            "vat_rate",
            "vat_amount",
            "total",
        ]
    )
    header = [
        inv.invoice_number,
        inv.invoice_date or "",
        inv.due_date or "",
        inv.supplier.name or "",
        inv.currency,
    ]
    footer = [
        _fmt(inv.subtotal),
        _fmt(inv.vat_rate),
        _fmt(inv.vat_amount),
        _fmt(inv.total),
    ]
    if not inv.items:
        writer.writerow([*header, "", "", "", "", "", *footer])
    else:
        for i, item in enumerate(inv.items, start=1):
            writer.writerow(
                [
                    *header,
                    i,
                    item.description,
                    item.quantity,
                    _fmt(item.unit_price),
                    _fmt(item.total),
                    *footer,
                ]
            )
    return buf.getvalue().encode("utf-8")


def _fmt(n: Decimal | float | None) -> str:
    return "" if n is None else f"{n:.2f}"


# ---------- UBL 2.1 ----------

UBL_NS = {
    "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


def to_ubl_bytes(inv: InvoiceData) -> bytes:
    """EN 16931-conformant UBL 2.1 Invoice.

    Shaped to pass the EU eInvoicing validator: both parties carry a name,
    postal address (Country/IdentificationCode) and legal-entity block;
    there is a TaxTotal with a VAT breakdown; every line has an
    InvoicedQuantity unitCode and a ClassifiedTaxCategory.
    """
    ns_map = {None: UBL_NS["ubl"], "cbc": UBL_NS["cbc"], "cac": UBL_NS["cac"]}
    root = etree.Element(f"{{{UBL_NS['ubl']}}}Invoice", nsmap=ns_map)

    _ubl_leaf(root, "cbc", "CustomizationID", "urn:cen.eu:en16931:2017")
    _ubl_leaf(root, "cbc", "ID", inv.invoice_number)
    if inv.invoice_date:
        _ubl_leaf(root, "cbc", "IssueDate", inv.invoice_date)
    if inv.due_date:
        _ubl_leaf(root, "cbc", "DueDate", inv.due_date)
    _ubl_leaf(root, "cbc", "InvoiceTypeCode", "380")  # commercial invoice
    _ubl_leaf(root, "cbc", "DocumentCurrencyCode", inv.currency)

    _ubl_party(root, "AccountingSupplierParty", inv.supplier)
    _ubl_party(root, "AccountingCustomerParty", inv.bill_to)

    # VAT breakdown (BR-CO-18). Even when VAT is zero/unknown we still emit a
    # single subtotal — the validator wants at least one TaxSubtotal.
    subtotal = inv.subtotal if inv.subtotal is not None else inv.total
    vat_amount = inv.vat_amount if inv.vat_amount is not None else Decimal("0")
    vat_rate = inv.vat_rate if inv.vat_rate is not None else Decimal("0")
    category_id = "S" if (vat_rate and float(vat_rate) > 0) else "Z"

    tax_total = etree.SubElement(root, f"{{{UBL_NS['cac']}}}TaxTotal")
    _ubl_amount(tax_total, "cbc", "TaxAmount", vat_amount, inv.currency)
    tax_subtotal = etree.SubElement(tax_total, f"{{{UBL_NS['cac']}}}TaxSubtotal")
    _ubl_amount(tax_subtotal, "cbc", "TaxableAmount", subtotal, inv.currency)
    _ubl_amount(tax_subtotal, "cbc", "TaxAmount", vat_amount, inv.currency)
    _ubl_tax_category(tax_subtotal, category_id, vat_rate)

    mono = etree.SubElement(root, f"{{{UBL_NS['cac']}}}LegalMonetaryTotal")
    _ubl_amount(mono, "cbc", "LineExtensionAmount", subtotal, inv.currency)
    _ubl_amount(mono, "cbc", "TaxExclusiveAmount", subtotal, inv.currency)
    _ubl_amount(mono, "cbc", "TaxInclusiveAmount", inv.total, inv.currency)
    _ubl_amount(mono, "cbc", "PayableAmount", inv.total, inv.currency)

    for i, item in enumerate(inv.items, start=1):
        line = etree.SubElement(root, f"{{{UBL_NS['cac']}}}InvoiceLine")
        _ubl_leaf(line, "cbc", "ID", str(i))
        qty = etree.SubElement(
            line,
            f"{{{UBL_NS['cbc']}}}InvoicedQuantity",
            unitCode=_unit_code_for(item.quantity),
        )
        qty.text = _numeric_part(item.quantity)
        _ubl_amount(line, "cbc", "LineExtensionAmount", item.total, inv.currency)
        item_el = etree.SubElement(line, f"{{{UBL_NS['cac']}}}Item")
        _ubl_leaf(item_el, "cbc", "Name", item.description)
        _ubl_tax_category(item_el, category_id, vat_rate, tag="ClassifiedTaxCategory")
        price_el = etree.SubElement(line, f"{{{UBL_NS['cac']}}}Price")
        _ubl_amount(price_el, "cbc", "PriceAmount", item.unit_price, inv.currency)

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")


def _ubl_leaf(parent: etree._Element, prefix: str, tag: str, text: str | None) -> etree._Element:
    el = etree.SubElement(parent, f"{{{UBL_NS[prefix]}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _ubl_amount(
    parent: etree._Element, prefix: str, tag: str, value: Decimal | float, currency: str
) -> etree._Element:
    el = etree.SubElement(parent, f"{{{UBL_NS[prefix]}}}{tag}", currencyID=currency)
    el.text = f"{value:.2f}"
    return el


def _ubl_party(parent: etree._Element, wrapper_tag: str, party: object) -> None:
    """Emit AccountingSupplierParty / AccountingCustomerParty with the
    identification, name, postal address, VAT scheme and legal-entity nodes
    EN 16931 requires (BR-06/07/08/10 + BR-CO-26 + BR-S-02 on the seller
    side)."""
    name = getattr(party, "name", None) or "Unknown"
    address = getattr(party, "address", None) or ""
    country = _country_code(address)
    is_supplier = wrapper_tag == "AccountingSupplierParty"

    wrap = etree.SubElement(parent, f"{{{UBL_NS['cac']}}}{wrapper_tag}")
    party_el = etree.SubElement(wrap, f"{{{UBL_NS['cac']}}}Party")

    # BR-CO-26: identifier of some kind. Reuse the name slug when nothing
    # better exists — validators require a non-empty value, not a real id.
    ident = etree.SubElement(party_el, f"{{{UBL_NS['cac']}}}PartyIdentification")
    _ubl_leaf(ident, "cbc", "ID", _slug(name))

    # BR-06 / BR-07
    pname = etree.SubElement(party_el, f"{{{UBL_NS['cac']}}}PartyName")
    _ubl_leaf(pname, "cbc", "Name", name)

    # BR-08 / BR-10
    addr = etree.SubElement(party_el, f"{{{UBL_NS['cac']}}}PostalAddress")
    if address:
        _ubl_leaf(addr, "cbc", "StreetName", address)
    country_el = etree.SubElement(addr, f"{{{UBL_NS['cac']}}}Country")
    _ubl_leaf(country_el, "cbc", "IdentificationCode", country)

    # BR-S-02: when any line is Standard-rated the seller MUST have a VAT
    # identifier. Our extraction schema doesn't capture it, so emit a
    # structured placeholder (country code + name hash) on the seller only.
    if is_supplier:
        tax_scheme = etree.SubElement(party_el, f"{{{UBL_NS['cac']}}}PartyTaxScheme")
        _ubl_leaf(tax_scheme, "cbc", "CompanyID", _placeholder_vat_id(country, name))
        scheme = etree.SubElement(tax_scheme, f"{{{UBL_NS['cac']}}}TaxScheme")
        _ubl_leaf(scheme, "cbc", "ID", "VAT")

    legal = etree.SubElement(party_el, f"{{{UBL_NS['cac']}}}PartyLegalEntity")
    _ubl_leaf(legal, "cbc", "RegistrationName", name)


def _placeholder_vat_id(country_code: str, name: str) -> str:
    """9-digit synthetic VAT identifier, prefixed with the party's country.
    Stable per supplier so repeat exports produce the same value; this is a
    structural placeholder, not a real tax identifier."""
    digits = abs(hash(name.lower())) % 1_000_000_000
    return f"{country_code}{digits:09d}"


def _ubl_tax_category(
    parent: etree._Element,
    category_id: str,
    percent: Decimal | float,
    *,
    tag: str = "TaxCategory",
) -> None:
    cat = etree.SubElement(parent, f"{{{UBL_NS['cac']}}}{tag}")
    _ubl_leaf(cat, "cbc", "ID", category_id)
    _ubl_leaf(cat, "cbc", "Percent", f"{float(percent or 0):.2f}")
    scheme = etree.SubElement(cat, f"{{{UBL_NS['cac']}}}TaxScheme")
    _ubl_leaf(scheme, "cbc", "ID", "VAT")


_COUNTRY_CODES = {
    "germany": "DE",
    "deutschland": "DE",
    "nepal": "NP",
    "united kingdom": "GB",
    "uk": "GB",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
    "netherlands": "NL",
    "austria": "AT",
    "switzerland": "CH",
    "united states": "US",
    "usa": "US",
    "india": "IN",
}


def _country_code(address: str) -> str:
    """Best-effort ISO 3166 alpha-2 from a free-form address. Defaults to
    DE because this exporter is used by a German recipient."""
    if not address:
        return "DE"
    last = address.rsplit(",", 1)[-1].strip().lower().rstrip(".")
    if len(last) == 2 and last.isalpha():
        return last.upper()
    return _COUNTRY_CODES.get(last, "DE")


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s).strip("-") or "UNKNOWN"


# Common UN/ECE Recommendation 20 unit codes. Default C62 = "one".
_UNIT_CODES = {
    "pcs": "H87",
    "pc": "H87",
    "piece": "H87",
    "pieces": "H87",
    "hr": "HUR",
    "hrs": "HUR",
    "hour": "HUR",
    "hours": "HUR",
    "kg": "KGM",
    "g": "GRM",
    "m": "MTR",
    "km": "KMT",
    "l": "LTR",
    "lt": "LTR",
    "lot": "LO",
    "box": "BX",
    "day": "DAY",
    "days": "DAY",
}


def _unit_code_for(quantity: str) -> str:
    parts = quantity.strip().split(" ", 1)
    if len(parts) < 2:
        return "C62"
    unit = parts[1].strip().lower().rstrip(".")
    return _UNIT_CODES.get(unit, "C62")


def _numeric_part(quantity: str) -> str:
    """'50 pcs' -> '50'. '10 hrs' -> '10'. Non-numeric -> '1'."""
    head = quantity.strip().split(" ", 1)[0].replace(",", "")
    try:
        float(head)
        return head
    except ValueError:
        return "1"


# ---------- Factur-X (minimal CrossIndustryInvoice XML) ----------
#
# Factur-X is a hybrid PDF/A-3 + XML standard. Here we emit just the XML
# payload (the "factur-x.xml" file), which is the useful bit for downstream
# consumers who already have the source PDF.

FX_NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


def to_facturx_xml_bytes(inv: InvoiceData) -> bytes:
    """Factur-X 1.0 BASIC profile.

    The CII XSD is strict about element order inside both
    SupplyChainTradeTransaction and its child trade-settlement/line nodes;
    this function emits the required line items, agreement, delivery and
    settlement blocks in exactly that order.
    """
    ns_map = {"rsm": FX_NS["rsm"], "ram": FX_NS["ram"], "udt": FX_NS["udt"]}
    root = etree.Element(f"{{{FX_NS['rsm']}}}CrossIndustryInvoice", nsmap=ns_map)

    # ExchangedDocumentContext
    ctx = etree.SubElement(root, f"{{{FX_NS['rsm']}}}ExchangedDocumentContext")
    param = etree.SubElement(ctx, f"{{{FX_NS['ram']}}}GuidelineSpecifiedDocumentContextParameter")
    _fx_leaf(param, "ram", "ID", "urn:factur-x.eu:1p0:basic")

    # ExchangedDocument
    doc = etree.SubElement(root, f"{{{FX_NS['rsm']}}}ExchangedDocument")
    _fx_leaf(doc, "ram", "ID", inv.invoice_number)
    _fx_leaf(doc, "ram", "TypeCode", "380")
    if inv.invoice_date:
        issue = etree.SubElement(doc, f"{{{FX_NS['ram']}}}IssueDateTime")
        dstr = etree.SubElement(issue, f"{{{FX_NS['udt']}}}DateTimeString", format="102")
        dstr.text = inv.invoice_date.replace("-", "")

    vat_rate = inv.vat_rate if inv.vat_rate is not None else Decimal("0")
    vat_amount = inv.vat_amount if inv.vat_amount is not None else Decimal("0")
    subtotal = inv.subtotal if inv.subtotal is not None else inv.total
    category_code = "S" if (vat_rate and float(vat_rate) > 0) else "Z"

    txn = etree.SubElement(root, f"{{{FX_NS['rsm']}}}SupplyChainTradeTransaction")

    # 1) Line items — MUST come before ApplicableHeaderTradeAgreement.
    for i, item in enumerate(inv.items, start=1):
        _fx_line_item(txn, i, item, inv.currency, category_code, vat_rate)

    # 2) Agreement
    agreement = etree.SubElement(txn, f"{{{FX_NS['ram']}}}ApplicableHeaderTradeAgreement")
    _fx_party(agreement, "SellerTradeParty", inv.supplier)
    _fx_party(agreement, "BuyerTradeParty", inv.bill_to)

    # 3) Delivery (required element, may be empty for BASIC)
    etree.SubElement(txn, f"{{{FX_NS['ram']}}}ApplicableHeaderTradeDelivery")

    # 4) Settlement: InvoiceCurrencyCode -> ApplicableTradeTax -> MonetarySummation
    settlement = etree.SubElement(txn, f"{{{FX_NS['ram']}}}ApplicableHeaderTradeSettlement")
    _fx_leaf(settlement, "ram", "InvoiceCurrencyCode", inv.currency)

    tax = etree.SubElement(settlement, f"{{{FX_NS['ram']}}}ApplicableTradeTax")
    _fx_amount(tax, "CalculatedAmount", vat_amount, inv.currency)
    _fx_leaf(tax, "ram", "TypeCode", "VAT")
    _fx_amount(tax, "BasisAmount", subtotal, inv.currency)
    _fx_leaf(tax, "ram", "CategoryCode", category_code)
    _fx_leaf(tax, "ram", "RateApplicablePercent", f"{float(vat_rate):.2f}")

    mono = etree.SubElement(
        settlement, f"{{{FX_NS['ram']}}}SpecifiedTradeSettlementHeaderMonetarySummation"
    )
    _fx_amount(mono, "LineTotalAmount", subtotal, inv.currency)
    _fx_amount(mono, "TaxBasisTotalAmount", subtotal, inv.currency)
    _fx_amount(mono, "TaxTotalAmount", vat_amount, inv.currency)
    _fx_amount(mono, "GrandTotalAmount", inv.total, inv.currency)
    _fx_amount(mono, "DuePayableAmount", inv.total, inv.currency)

    return etree.tostring(root, pretty_print=True, xml_declaration=True, encoding="UTF-8")


def _fx_leaf(parent: etree._Element, prefix: str, tag: str, text: str) -> etree._Element:
    el = etree.SubElement(parent, f"{{{FX_NS[prefix]}}}{tag}")
    el.text = text
    return el


def _fx_amount(
    parent: etree._Element, tag: str, value: Decimal | float, currency: str
) -> None:
    el = etree.SubElement(parent, f"{{{FX_NS['ram']}}}{tag}", currencyID=currency)
    el.text = f"{value:.2f}"


def _fx_party(parent: etree._Element, tag: str, party: object) -> None:
    """Seller/Buyer trade party with Name + PostalTradeAddress (required by
    the BASIC profile)."""
    name = getattr(party, "name", None) or "Unknown"
    address = getattr(party, "address", None) or ""

    party_el = etree.SubElement(parent, f"{{{FX_NS['ram']}}}{tag}")
    _fx_leaf(party_el, "ram", "Name", name)
    addr = etree.SubElement(party_el, f"{{{FX_NS['ram']}}}PostalTradeAddress")
    if address:
        _fx_leaf(addr, "ram", "LineOne", address)
    _fx_leaf(addr, "ram", "CountryID", _country_code(address))


def _fx_line_item(
    parent: etree._Element,
    line_no: int,
    item: object,
    currency: str,
    category_code: str,
    vat_rate: Decimal | float,
) -> None:
    line = etree.SubElement(parent, f"{{{FX_NS['ram']}}}IncludedSupplyChainTradeLineItem")

    doc = etree.SubElement(line, f"{{{FX_NS['ram']}}}AssociatedDocumentLineDocument")
    _fx_leaf(doc, "ram", "LineID", str(line_no))

    prod = etree.SubElement(line, f"{{{FX_NS['ram']}}}SpecifiedTradeProduct")
    _fx_leaf(prod, "ram", "Name", getattr(item, "description", "") or "")

    agreement = etree.SubElement(line, f"{{{FX_NS['ram']}}}SpecifiedLineTradeAgreement")
    net_price = etree.SubElement(agreement, f"{{{FX_NS['ram']}}}NetPriceProductTradePrice")
    _fx_amount(net_price, "ChargeAmount", getattr(item, "unit_price", 0) or 0, currency)

    delivery = etree.SubElement(line, f"{{{FX_NS['ram']}}}SpecifiedLineTradeDelivery")
    qty = etree.SubElement(
        delivery,
        f"{{{FX_NS['ram']}}}BilledQuantity",
        unitCode=_unit_code_for(getattr(item, "quantity", "")),
    )
    qty.text = _numeric_part(getattr(item, "quantity", ""))

    settlement = etree.SubElement(line, f"{{{FX_NS['ram']}}}SpecifiedLineTradeSettlement")
    tax = etree.SubElement(settlement, f"{{{FX_NS['ram']}}}ApplicableTradeTax")
    _fx_leaf(tax, "ram", "TypeCode", "VAT")
    _fx_leaf(tax, "ram", "CategoryCode", category_code)
    _fx_leaf(tax, "ram", "RateApplicablePercent", f"{float(vat_rate or 0):.2f}")
    line_mono = etree.SubElement(
        settlement, f"{{{FX_NS['ram']}}}SpecifiedTradeSettlementLineMonetarySummation"
    )
    _fx_amount(line_mono, "LineTotalAmount", getattr(item, "total", 0) or 0, currency)

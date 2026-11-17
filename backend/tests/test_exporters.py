from __future__ import annotations

import json

from lxml import etree

from app.schemas import InvoiceData, InvoiceItem, Party
from app.services.exporters import to_csv_bytes, to_facturx_xml_bytes, to_json_bytes, to_ubl_bytes


def _inv() -> InvoiceData:
    return InvoiceData(
        invoice_number="RT-2024-1052",
        invoice_date="2024-10-14",
        due_date="2024-11-13",
        supplier=Party(name="Rivertech Supplies Ltd."),
        bill_to=Party(name="Deutschelink GmbH"),
        items=[
            InvoiceItem(description="HDPE Pipe 110mm", quantity="50 pcs", unit_price=1250.0, total=62500.0),
            InvoiceItem(description="Delivery", quantity="1 lot", unit_price=5000.0, total=5000.0),
        ],
        subtotal=67500.0,
        vat_rate=13.0,
        vat_amount=8775.0,
        total=76275.0,
        currency="NPR",
    )


def test_json_round_trips() -> None:
    data = json.loads(to_json_bytes(_inv()).decode())
    assert data["invoice_number"] == "RT-2024-1052"
    assert data["items"][0]["quantity"] == "50 pcs"
    assert data["total"] == 76275.0


def test_csv_has_header_and_row_per_item() -> None:
    text = to_csv_bytes(_inv()).decode()
    lines = text.splitlines()
    assert lines[0].startswith("invoice_number,")
    # 1 header + 2 item rows
    assert len(lines) == 3
    assert "HDPE Pipe 110mm" in lines[1]
    assert "Delivery" in lines[2]


def test_ubl_is_valid_xml_with_expected_nodes() -> None:
    xml = to_ubl_bytes(_inv())
    root = etree.fromstring(xml)
    ns = {
        "ubl": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }
    assert root.tag == f"{{{ns['ubl']}}}Invoice"
    assert root.find("cbc:ID", ns).text == "RT-2024-1052"
    assert root.find("cbc:DocumentCurrencyCode", ns).text == "NPR"
    lines = root.findall("cac:InvoiceLine", ns)
    assert len(lines) == 2


def test_facturx_is_valid_xml_with_expected_nodes() -> None:
    xml = to_facturx_xml_bytes(_inv())
    root = etree.fromstring(xml)
    ns = {
        "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    }
    assert root.tag == f"{{{ns['rsm']}}}CrossIndustryInvoice"
    doc = root.find("rsm:ExchangedDocument", ns)
    assert doc.find("ram:ID", ns).text == "RT-2024-1052"

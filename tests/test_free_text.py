"""Rule-based reading of RFQ items from free text (emails, pasted text)."""

import pytest

from src.extract_rfq import NoLineItemsError, extract_rfq_from_text
from src.parse_free_text import lines_from_text, parse_item_line


def rows(text):
    return lines_from_text(text, "email body").to_dict("records")


def test_numbered_list_email_with_signature_and_reply():
    text = """Dear Sales Team,

Please quote your best price for the following items:

1. ABB MCB 3 pole 32A C curve, 1SYS273022R0324 - 24 nos
2. Schneider MCCB LV510347 100A 4P - 4 Nos
3) Contactor 26A coil 230V AC, Qty: 8
4. Thermal overload relay 18-25A (part code to be confirmed) - 6 pcs

Delivery required within 2 weeks. Prices in GBP please.

Best regards,
Daniel Hart
Kestrel Building Services Ltd
Tel: +44 113 000 0000

On Mon, 12 Oct 2026 at 10:00, Someone wrote:
> 9. Old item 99 nos
"""
    found = rows(text)
    assert [r["line_no"] for r in found] == ["1", "2", "3", "4"]

    first = found[0]
    assert first["make"] == "ABB"
    assert first["part_code"] == "1SYS273022R0324"
    assert first["qty"] == 24 and first["unit"].lower() == "nos"
    assert "MCB" in first["description"] and "32A" in first["description"]

    assert found[1]["make"] == "Schneider Electric"
    assert found[1]["part_code"] == "LV510347"
    assert found[1]["qty"] == 4

    assert found[2]["qty"] == 8
    assert found[2]["part_code"] == ""          # 26A / 230V are specs, not codes

    assert found[3]["part_code"] == ""
    assert "confirmed" in found[3]["code_note"]
    assert found[3]["qty"] == 6


def test_quantity_times_forms():
    found = rows("5 x ABB MCB 16A SP 1SYS271012R0164\nLED pilot lamp green 24V x 30")
    assert found[0]["qty"] == 5 and found[0]["part_code"] == "1SYS271012R0164"
    assert found[1]["qty"] == 30 and "pilot lamp" in found[1]["description"].lower()


def test_labelled_blocks():
    text = """Item 1
Description: Air Circuit Breaker 1600A 3P draw-out
Make: Schneider
Part No: TBC
Qty: 1 No

Item 2
Description: Earth leakage relay Vigirex RH10
Make: Schneider Electric
Part No: 56130
Quantity: 3 Nos
"""
    found = rows(text)
    assert len(found) == 2
    assert found[0]["line_no"] == "1"
    assert found[0]["description"].startswith("Air Circuit Breaker")
    assert found[0]["make"] == "Schneider Electric"
    assert found[0]["part_code"] == "" and found[0]["code_note"] == "TBC"
    assert found[0]["qty"] == 1
    assert found[1]["part_code"] == "56130" and found[1]["qty"] == 3


def test_pasted_table_with_tabs():
    text = "Hi,\n\nS.No\tDescription\tMake\tPart Code\tQty\tUnit\n" \
           "1\tMCB 32A 3P\tABB\t1SYS273022R0324\t24\tNos\n" \
           "2\tRCCB 40A 4P 30mA\tABB\t1SYF204015R1400\t12\tNos\n\nThanks"
    found = rows(text)
    assert len(found) == 2
    assert found[1]["part_code"] == "1SYF204015R1400"
    assert found[1]["qty"] == 12
    assert "pasted table" in found[0]["source"]


def test_prose_lines_are_ignored():
    assert parse_item_line("Please send your quotation within 3 days.") is None
    assert parse_item_line("Our ref: KBS/RFQ/2026/0147") is None
    assert parse_item_line("Delivery: 2 weeks from PO") is None
    assert parse_item_line("Dear Sir/Madam,") is None


def test_specs_are_not_part_codes():
    item = parse_item_line("1. MCCB 250A 4P 36kA 415V IP65 - 2 nos")
    assert item["part_code"] == ""
    assert item["qty"] == 2


def test_items_only_in_quoted_reply_are_used():
    text = "Please see the list below.\n\nOn Tue, Someone wrote:\n> 1. ABB MCB 32A 1SYS273022R0324 - 10 nos"
    found = rows(text)
    assert len(found) == 1 and found[0]["qty"] == 10


def test_pasted_text_entry_point_and_header():
    text = """Subject: RFQ No. KBS/RFQ/2026/0200

Please quote by 30 October 2026, prices in GBP:
1. ABB MCB 32A 3P 1SYS273022R0324 - 24 nos

Regards,
Daniel Hart
Kestrel Building Services Ltd
Tel: +44 113 000 0000
procurement@kestrel-bs.example
"""
    lines, header = extract_rfq_from_text(text)
    assert len(lines) == 1
    assert header["rfq_number"] == "KBS/RFQ/2026/0200"
    assert header["due_date"] == "30/10/2026"
    assert header["currency"] == "GBP"
    assert header["customer_name"] == "Kestrel Building Services Ltd"
    assert header["contact_person"] == "Daniel Hart"
    assert header["phone"] == "+44 113 000 0000"
    assert header["email"] == "procurement@kestrel-bs.example"


def test_no_items_raises():
    with pytest.raises(NoLineItemsError):
        extract_rfq_from_text("Hello, please call me back about the project. Thanks")


def test_make_written_after_the_item():
    item = parse_item_line("1) MCCB 4P 250A 36kA ABB make - 2 Nos.")
    assert item["make"] == "ABB"
    assert item["description"] == "MCCB 4P 250A 36kA"
    assert item["qty"] == 2


def test_uk_style_quantities():
    found = rows("- 12 x LV429630 Schneider NSX100 trip unit\n- 1 off Lucy Aegis Plus RMU\n• 20 no. 2CTB803973R1100 SPD")
    assert [r["qty"] for r in found] == [12, 1, 20]
    assert found[1]["make"] == "Lucy Electric"
    assert found[2]["part_code"] == "2CTB803973R1100"


def test_several_items_on_one_line():
    found = rows("Please quote: ABB S203-C32 MCB 3P 32A, 24 pcs; Schneider A9F74232 MCB, 10 pcs; "
                 "Siemens 5SL6332-7 MCB, 8 pcs.")
    assert [r["part_code"] for r in found] == ["S203-C32", "A9F74232", "5SL6332-7"]
    assert [r["qty"] for r in found] == [24, 10, 8]


def test_cable_lengths_and_sets():
    found = rows("1. 4C x 95 sqmm XLPE armoured cable - 250 m\n2. Cable glands 32mm - 40 sets")
    assert [(r["qty"], r["unit"]) for r in found] == [(250, "m"), (40, "sets")]


def test_chatty_reply_is_not_an_item():
    text = ("Yes please go ahead with the same as last time but qty 30.\n\nRegards\nAnn\n\n"
            "-----Original Message-----\nFrom: Sales\n\n1. ABB 1SYS273022R0324 MCB 32A 3P - 20 nos")
    found = rows(text)
    assert len(found) == 1 and found[0]["part_code"] == "1SYS273022R0324"

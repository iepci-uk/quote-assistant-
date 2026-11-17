"""RFQs that arrive as emails (.eml) - body text and attached RFQ files."""

from email.message import EmailMessage
from pathlib import Path

import pytest

from src.extract_rfq import NoLineItemsError, extract_rfq_header, extract_rfq_lines

RFQ = Path(__file__).resolve().parent.parent / "data" / "raw" / "RFQ_KBS-0147.pdf"

BODY = """Hello IEPCI team,

Further to our RFQ please also add these to your quote:

1. ABB MCB 3 pole 32A C curve 1SYS273022R0324 - 10 nos
2. Schneider shunt trip LV429387 - 2 nos

Please quote by 30/10/2026.

Kind regards,
Daniel Hart
Procurement Manager
Kestrel Building Services Ltd
Tel: +44 113 000 0000
"""


def make_eml(folder: Path, body: str, attach: Path = None) -> Path:
    message = EmailMessage()
    message["From"] = "Daniel Hart <procurement@kestrel-bs.example>"
    message["To"] = "info@iepci.co.uk"
    message["Subject"] = "RE: RFQ KBS/RFQ/2026/0147 - LV panel"
    message["Date"] = "Thu, 15 Oct 2026 09:30:00 +0100"
    message.set_content(body)
    if attach is not None:
        message.add_attachment(attach.read_bytes(), maintype="application",
                               subtype="pdf", filename=attach.name)
    path = folder / "enquiry.eml"
    path.write_bytes(bytes(message))
    return path


def test_items_in_email_body(tmp_path):
    lines = extract_rfq_lines(make_eml(tmp_path, BODY))
    assert list(lines["part_code"]) == ["1SYS273022R0324", "LV429387"]
    assert list(lines["qty"]) == [10, 2]
    assert all(s.startswith("email body") for s in lines["source"])


def test_email_header(tmp_path):
    header = extract_rfq_header(make_eml(tmp_path, BODY))
    assert header["email"] == "procurement@kestrel-bs.example"
    assert header["contact_person"] == "Daniel Hart"
    assert header["rfq_number"] == "KBS/RFQ/2026/0147"
    assert header["rfq_date"] == "15/10/2026"
    assert header["due_date"] == "30/10/2026"
    assert header["phone"] == "+44 113 000 0000"
    assert header["customer_name"] == "Kestrel Building Services Ltd"


def test_html_only_email(tmp_path):
    message = EmailMessage()
    message["From"] = "buyer@example.com"
    message["Subject"] = "Enquiry"
    message.set_content(
        "<html><body><p>Please quote:</p><table>"
        "<tr><th>No</th><th>Description</th><th>Make</th><th>Part Code</th><th>Qty</th></tr>"
        "<tr><td>1</td><td>MCCB 100A 4P</td><td>Schneider</td><td>LV510347</td><td>4</td></tr>"
        "</table></body></html>",
        subtype="html",
    )
    path = tmp_path / "html.eml"
    path.write_bytes(bytes(message))
    lines = extract_rfq_lines(path)
    assert list(lines["part_code"]) == ["LV510347"]
    assert lines["qty"][0] == 4


@pytest.mark.skipif(not RFQ.exists(), reason="Put RFQ_KBS-0147.pdf in data/raw/ first.")
def test_attachment_and_body_are_combined(tmp_path):
    lines = extract_rfq_lines(make_eml(tmp_path, BODY, attach=RFQ))
    from_body = lines[lines["source"].str.startswith("email body")]
    from_pdf = lines[lines["source"].str.startswith("attachment RFQ_KBS-0147.pdf")]
    assert len(from_body) == 2
    assert len(from_pdf) == 20

    header = extract_rfq_header(make_eml(tmp_path, BODY, attach=RFQ))
    assert header["address"].startswith("Unit 4")      # filled from the PDF
    assert header["currency"] == "GBP"


def test_email_without_items(tmp_path):
    with pytest.raises(NoLineItemsError):
        extract_rfq_lines(make_eml(tmp_path, "Hi, can you call me about the project?\n\nThanks"))


def test_plain_text_file(tmp_path):
    path = tmp_path / "rfq.txt"
    path.write_text("Need 5 x ABB 1SYS271012R0164 MCB 16A\n", encoding="utf-8")
    lines = extract_rfq_lines(path)
    assert lines["qty"][0] == 5 and lines["part_code"][0] == "1SYS271012R0164"

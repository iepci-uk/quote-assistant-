"""Scanned RFQs (OCR) and RFQs written as email text.

The scans are made in the test from the Kestrel RFQ, so OCR must give the
same lines as reading the text PDF: every code, quantity, make and unit.
The OCR tests are skipped if Tesseract is not installed.

Run from the project root:
    python -m pytest
"""

from email.message import EmailMessage
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image, ImageFilter

from src.code_correction import CodeIndex, correct_codes
from src.extract_rfq import extract_rfq_from_text, extract_rfq_header, extract_rfq_lines
from src.load_price_lists import load_catalogue, make_key

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RFQ = RAW / "RFQ_KBS-0147.pdf"
ABB = RAW / "ABB_Price_List_Feb2026.xlsx"
SCHNEIDER = RAW / "Schneider LV Price list Apr 2026.xlsx"

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in (RFQ, ABB, SCHNEIDER)),
    reason="Put the RFQ and both price lists in data/raw/ first.",
)


def tesseract_installed():
    try:
        from src.ocr_rfq import find_tesseract

        find_tesseract()
        return True
    except (ImportError, RuntimeError):
        return False


needs_ocr = pytest.mark.skipif(not tesseract_installed(), reason="Tesseract OCR is not installed.")


@pytest.fixture(scope="module")
def catalogue():
    return load_catalogue(ABB, SCHNEIDER)


@pytest.fixture(scope="module")
def expected():
    return extract_rfq_lines(RFQ)


def page_images(dpi):
    import pdfplumber

    with pdfplumber.open(RFQ) as pdf:
        return [page.to_image(resolution=dpi).original.convert("RGB") for page in pdf.pages]


def degraded(image, angle, seed):
    """A poor scan: tilted, grainy and slightly blurred."""
    image = image.convert("L").rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    pixels = np.array(image).astype(float) + np.random.default_rng(seed).normal(0, 18, image.size[::-1])
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))


@pytest.fixture(scope="module")
def scans(tmp_path_factory):
    folder = tmp_path_factory.mktemp("scans")
    clean = page_images(300)
    clean[0].save(folder / "clean.pdf", save_all=True, append_images=clean[1:], resolution=300)
    poor = [degraded(page, angle, n) for n, (page, angle) in enumerate(zip(page_images(200), (1.5, -2.0)))]
    poor[0].save(folder / "poor.pdf", save_all=True, append_images=poor[1:], resolution=200)
    clean[1].rotate(90, expand=True).save(folder / "sideways.png")
    if tesseract_installed():
        from src.ocr_rfq import lines_removed, to_gray

        Image.fromarray(lines_removed(to_gray(clean[0]))).save(folder / "unruled.png")
    return folder


def same_as_text_pdf(lines, expected):
    lines = lines.set_index("line_no")
    expected = expected.set_index("line_no")
    assert list(lines.index) == list(expected.index)
    for line_no, want in expected.iterrows():
        got = lines.loc[line_no]
        assert make_key(got["part_code"]) == make_key(want["part_code"]), line_no
        assert float(got["qty"]) == float(want["qty"]), line_no
        assert got["make"] == want["make"], line_no
        assert got["unit"] == want["unit"], line_no


# ------------------------------------------------------------ OCR
@needs_ocr
@pytest.mark.parametrize("name", ["clean.pdf", "poor.pdf"])
def test_scanned_rfq_reads_like_the_text_pdf(scans, name, catalogue, expected):
    lines = extract_rfq_lines(scans / name, catalogue)
    same_as_text_pdf(lines, expected)
    assert lines["source"].str.contains("(OCR", regex=False).all()


@needs_ocr
def test_every_ocr_correction_is_noted(scans, catalogue, expected):
    lines = extract_rfq_lines(scans / "poor.pdf", catalogue)
    original = expected.set_index("line_no")["part_code"]
    for line in lines.itertuples():
        if line.part_code != original[line.line_no] and line.part_code:
            assert "corrected" in line.code_note


@needs_ocr
def test_sideways_photo_of_page_two(scans, catalogue, expected):
    lines = extract_rfq_lines(scans / "sideways.png", catalogue)
    same_as_text_pdf(lines, expected[expected["line_no"].astype(int) >= 12])


@needs_ocr
def test_table_without_ruling_lines(scans, catalogue, expected):
    lines = extract_rfq_lines(scans / "unruled.png", catalogue)
    same_as_text_pdf(lines, expected[expected["line_no"].astype(int) <= 11])
    assert extract_rfq_header(scans / "unruled.png")["rfq_number"] == "KBS/RFQ/2026/0147"


@needs_ocr
def test_scanned_header(scans):
    assert extract_rfq_header(scans / "clean.pdf") == extract_rfq_header(RFQ)


# ------------------------------------------------------------ code correction
def scanned(code, make="ABB"):
    return pd.DataFrame([{"line_no": "1", "description": "", "make": make, "part_code": code,
                          "code_note": "", "qty": 1, "unit": "", "source": "page 1 (OCR)"}])


def test_look_alike_characters_are_corrected(catalogue):
    fixed = correct_codes(scanned("1SDA067O18RI"), CodeIndex(catalogue)).iloc[0]
    assert fixed["part_code"] == "1SDA067018R1"
    assert "corrected" in fixed["code_note"]


def test_symbol_read_for_a_letter_is_corrected(catalogue):
    fixed = correct_codes(scanned("1$AZ211201R2051"), CodeIndex(catalogue)).iloc[0]
    assert fixed["part_code"] == "1SAZ211201R2051"


def test_unknown_scanned_code_is_kept_and_flagged(catalogue):
    fixed = correct_codes(scanned("ZZZ999999"), CodeIndex(catalogue)).iloc[0]
    assert fixed["part_code"] == "ZZZ999999"
    assert "check" in fixed["code_note"]


def test_typed_codes_are_never_changed(catalogue):
    fixed = correct_codes(scanned("1SDA067018R2"), CodeIndex(catalogue), typed=True).iloc[0]
    assert fixed["part_code"] == "1SDA067018R2"
    assert "closest is 1SDA067018R1" in fixed["code_note"]


# ------------------------------------------------------------ email text
EMAIL = """Dear Sir,

Please send your best price for the below items.
RFQ No: KBS/RFQ/2026/0200. Kindly quote by 12 November 2026 in GBP.

1. ABB MCB 3 pole 32A C curve, 1SYS273022R0324 - 24 nos
2. ABB MCB 1P 16A, part no 1SYS 271012 R0164, qty 60
3) Schneider MCCB EasyPact CVS100 100A 4P LV510347 x 4
4. ABB ACB Formula Air 1000A 3P drawout, part code to be confirmed - 1 no
5. Aux contact OF/SD/SDE for NSX, 29450, 12 nos

Regards,
Daniel Hart
Procurement Manager
Kestrel Building Services Ltd
Tel: +44 113 000 0000
"""


def test_numbered_email_items(catalogue):
    lines, header = extract_rfq_from_text(EMAIL, catalogue)
    assert list(lines["line_no"]) == ["1", "2", "3", "4", "5"]
    assert list(lines["qty"]) == [24, 60, 4, 1, 12]
    assert [make_key(c) for c in lines["part_code"]] == [
        "1SYS273022R0324", "1SYS271012R0164", "LV510347", "", "29450"]
    assert list(lines["make"]) == ["ABB", "ABB", "Schneider Electric", "ABB", "Schneider Electric"]
    assert "to be confirmed" in lines.loc[3, "code_note"]
    assert lines.loc[0, "description"] == "ABB MCB 3 pole 32A C curve"


def test_email_header_details(catalogue):
    _, header = extract_rfq_from_text(EMAIL, catalogue)
    assert header["rfq_number"] == "KBS/RFQ/2026/0200"
    assert header["due_date"] == "12 November 2026"
    assert header["currency"] == "GBP"
    assert header["customer_name"] == "Kestrel Building Services Ltd"
    assert header["contact_person"] == "Daniel Hart"
    assert header["phone"] == "+44 113 000 0000"


def test_table_pasted_into_email(catalogue):
    text = ("Please quote:\n\nS.No\tDescription\tMake\tPart No\tQty\tUnit\n"
            "1\tMCB 3P 32A\tABB\t1SYS273022R0324\t24\tNos\n"
            "2\tMCCB 100A 4P\tSchneider\tLV510347\t4\tNos\n\nThanks")
    lines, _ = extract_rfq_from_text(text, catalogue)
    assert list(lines["part_code"]) == ["1SYS273022R0324", "LV510347"]
    assert list(lines["qty"]) == [24, 4]


def test_labelled_blocks(catalogue):
    text = ("Item 1\nDescription: MCCB 250A 3P\nMake: Schneider\nPart No: C25F32D250\nQty: 2 nos\n\n"
            "Item 2\nDescription: Earth leakage relay\nMake: Schneider\nPart No: 56130\nQty: 3\n")
    lines, _ = extract_rfq_from_text(text, catalogue)
    assert list(lines["part_code"]) == ["C25F32D250", "56130"]
    assert list(lines["qty"]) == [2, 3]


def test_two_quantities_are_not_guessed(catalogue):
    lines, _ = extract_rfq_from_text("1. MCB 16A 10 nos or 12 nos, 1SYS271012R0164\n", catalogue)
    assert pd.isna(lines.loc[0, "qty"])
    assert "check qty" in lines.loc[0, "code_note"]


def test_sentences_are_not_items(catalogue):
    text = "We need 2 sets of drawings with the offer.\nPlease quote ABB 1SFA619403R5022 pilot lamp 30 nos.\n"
    lines, _ = extract_rfq_from_text(text, catalogue)
    assert len(lines) == 1
    assert lines.loc[0, "part_code"] == "1SFA619403R5022"


def test_text_without_items_is_rejected(catalogue):
    with pytest.raises(ValueError, match="No RFQ items"):
        extract_rfq_from_text("Hi, can you call me tomorrow?\nThanks", catalogue)


# ------------------------------------------------------------ email files
def test_eml_with_html_table(tmp_path, catalogue):
    message = EmailMessage()
    message["From"] = "Priya Shah <priya@acme-power.example>"
    message["Subject"] = "RE: RFQ ACM/2026/77 - Substation LV panel"
    message["Date"] = "Mon, 2 Nov 2026 10:15:00 +0530"
    message.set_content("Please quote, table below.")
    message.add_alternative(
        "<table><tr><th>Sr No</th><th>Item Description</th><th>Make</th><th>Cat No</th><th>Qty</th>"
        "<th>UOM</th></tr><tr><td>1</td><td>RCCB 4P 40A</td><td>ABB</td><td>1SYF204015R1400</td>"
        "<td>12</td><td>Nos</td></tr></table>", subtype="html")
    path = tmp_path / "rfq.eml"
    path.write_bytes(bytes(message))

    lines = extract_rfq_lines(path, catalogue)
    assert list(lines["part_code"]) == ["1SYF204015R1400"]
    header = extract_rfq_header(path)
    assert header["rfq_number"] == "ACM/2026/77"
    assert header["project"] == "Substation LV panel"
    assert header["rfq_date"] == "02/11/2026"
    assert header["email"] == "priya@acme-power.example"


def test_eml_with_rfq_attached(tmp_path, catalogue, expected):
    message = EmailMessage()
    message["From"] = "Daniel Hart <procurement@kestrel-bs.example>"
    message["Subject"] = "RFQ attached"
    message.set_content("Hi, RFQ attached.\n\nRegards,\nDaniel")
    message.add_attachment(RFQ.read_bytes(), maintype="application", subtype="pdf", filename="RFQ.pdf")
    path = tmp_path / "rfq.eml"
    path.write_bytes(bytes(message))

    same_as_text_pdf(extract_rfq_lines(path, catalogue), expected)
    assert extract_rfq_header(path)["rfq_number"] == "KBS/RFQ/2026/0147"


def test_txt_file(tmp_path, catalogue):
    path = tmp_path / "rfq.txt"
    path.write_text(EMAIL, encoding="cp1252")
    assert len(extract_rfq_lines(path, catalogue)) == 5

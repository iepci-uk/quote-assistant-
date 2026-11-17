"""Scanned PDFs: the Kestrel RFQ turned into an image-only PDF must give the
same lines as the original - also when the scan is tilted or noisy.
OCR takes about 30 seconds per scanned copy (two pages)."""

from pathlib import Path

import pytest

from src.extract_rfq import extract_rfq_header, extract_rfq_lines, pdf_has_scanned_pages
from src.load_price_lists import make_key

RFQ = Path(__file__).resolve().parent.parent / "data" / "raw" / "RFQ_KBS-0147.pdf"

pytest.importorskip("rapidocr_onnxruntime")
pytestmark = pytest.mark.skipif(not RFQ.exists(), reason="Put RFQ_KBS-0147.pdf in data/raw/ first.")


@pytest.fixture(scope="module")
def scanned_pdf(tmp_path_factory):
    """Render each page to a 200 dpi image and save the images as a PDF -
    the same thing a scanner produces (no text layer)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(RFQ))
    images = [pdf[i].render(scale=200 / 72).to_pil().convert("RGB") for i in range(len(pdf))]
    pdf.close()
    path = tmp_path_factory.mktemp("scan") / "RFQ_scanned.pdf"
    images[0].save(path, save_all=True, append_images=images[1:], resolution=200)
    return path


def test_scan_has_no_text_layer(scanned_pdf):
    assert pdf_has_scanned_pages(scanned_pdf)
    assert not pdf_has_scanned_pages(RFQ)


def test_scanned_lines_match_original(scanned_pdf):
    original = extract_rfq_lines(RFQ)
    scanned = extract_rfq_lines(scanned_pdf)

    assert len(scanned) == len(original) == 20
    assert list(scanned["line_no"]) == list(original["line_no"])
    assert list(scanned["qty"]) == list(original["qty"])
    assert list(scanned["make"]) == list(original["make"])
    same_codes = sum(
        make_key(a) == make_key(b) for a, b in zip(scanned["part_code"], original["part_code"])
    )
    assert same_codes >= 18
    # Lines 12 and 18 have no code, only a note.
    for line in ("12", "18"):
        row = scanned[scanned["line_no"] == line].iloc[0]
        assert row["part_code"] == "" and "supplier" in row["code_note"]
    assert all("OCR" in s for s in scanned["source"])


def test_scanned_header(scanned_pdf):
    header = extract_rfq_header(scanned_pdf)
    assert header["customer_name"] == "Kestrel Building Services Ltd"
    assert header["rfq_number"] == "KBS/RFQ/2026/0147"
    assert header["rfq_date"] == "15/10/2026"
    assert header["email"] == "procurement@kestrel-bs.example"
    assert header["currency"] == "GBP"
    assert header["address"].startswith("Unit 4")
    assert "QUOTATION" not in header["address"].upper()


def _scan(folder, name, change):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(RFQ))
    images = [change(pdf[i].render(scale=200 / 72).to_pil().convert("RGB")) for i in range(len(pdf))]
    pdf.close()
    path = folder / f"{name}.pdf"
    images[0].save(path, save_all=True, append_images=images[1:], resolution=200)
    return path


def _tilted(image):
    return image.rotate(1.5, expand=True, fillcolor="white")


def _noisy(image):
    import io

    import numpy as np
    from PIL import Image

    grey = np.array(image.convert("L")).astype(np.int16)
    grey = grey + np.random.default_rng(1).normal(0, 18, grey.shape)
    buffer = io.BytesIO()
    Image.fromarray(np.clip(grey, 0, 255).astype(np.uint8)).save(buffer, "JPEG", quality=35)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


@pytest.mark.parametrize("change", [_tilted, _noisy], ids=["tilted", "noisy"])
def test_hard_scans(tmp_path, change):
    """A page fed in at an angle, and a noisy low-quality JPEG scan: the
    tilt is levelled, and cells OCR missed (lone '1's) are read again."""
    original = extract_rfq_lines(RFQ)
    scanned = extract_rfq_lines(_scan(tmp_path, change.__name__, change))
    assert list(scanned["line_no"]) == list(original["line_no"])
    assert list(scanned["qty"]) == list(original["qty"])
    assert [make_key(c) for c in scanned["part_code"]] == [make_key(c) for c in original["part_code"]]

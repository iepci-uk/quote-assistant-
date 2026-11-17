"""RFQ documents without a ruled table: a PDF table drawn without lines, and
a Word file with the items written as paragraphs."""

import ctypes

import docx

from src.extract_rfq import extract_rfq_lines


def text_pdf(path, items):
    """Write a one-page A4 PDF. items: (x, y_from_top, text), Helvetica 10 pt."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(595, 842)
    for x, y, text in items:
        obj = raw.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", ctypes.c_float(10))
        buffer = ctypes.create_string_buffer((text + "\0").encode("utf-16-le"))
        raw.FPDFText_SetText(obj, ctypes.cast(buffer, ctypes.POINTER(raw.FPDF_WCHAR)))
        raw.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, 842 - y)
        raw.FPDFPage_InsertObject(page.raw, obj)
    raw.FPDFPage_GenerateContent(page.raw)
    pdf.save(str(path))
    pdf.close()


def test_pdf_table_without_lines(tmp_path):
    columns = [(40, "No."), (80, "Description"), (330, "Make"), (400, "Part Code"), (500, "Qty"), (540, "Unit")]
    items = [(40, 60, "ACME Engineering Ltd"), (40, 90, "Request for Quotation")]
    items += [(x, 140, title) for x, title in columns]
    data = [
        ("1", "MCB 3 pole 32A C curve", "ABB", "1SYS273022R0324", "24", "Nos"),
        ("2", "MCCB 100A 4 pole 36kA", "Schneider", "LV510347", "4", "Nos"),
    ]
    y = 160
    for row in data:
        items += [(x, y, value) for (x, _), value in zip(columns, row)]
        items.append((80, y + 12, "DIN rail mounted"))      # description wraps
        y += 36
    path = tmp_path / "borderless.pdf"
    text_pdf(path, items)

    lines = extract_rfq_lines(path)
    assert list(lines["part_code"]) == ["1SYS273022R0324", "LV510347"]
    assert list(lines["qty"]) == [24, 4]
    assert list(lines["make"]) == ["ABB", "Schneider Electric"]
    assert lines["description"][0] == "MCB 3 pole 32A C curve DIN rail mounted"
    assert all("text layout" in s for s in lines["source"])


def test_word_file_with_items_as_paragraphs(tmp_path):
    document = docx.Document()
    document.add_paragraph("Request for Quotation")
    document.add_paragraph("Please quote for the following:")
    document.add_paragraph("1. ABB MCB 32A 3 pole 1SYS273022R0324 - 24 nos")
    document.add_paragraph("2. Schneider MCCB LV510347 100A 4P - 4 nos")
    path = tmp_path / "prose.docx"
    document.save(path)

    lines = extract_rfq_lines(path)
    assert list(lines["part_code"]) == ["1SYS273022R0324", "LV510347"]
    assert list(lines["qty"]) == [24, 4]
    assert lines["source"][0].startswith("text, line")

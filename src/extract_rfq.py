"""Read an RFQ file (PDF, Word, Excel or email) and return its line items.

    from extract_rfq import extract_rfq_lines
    lines = extract_rfq_lines("data/raw/RFQ_KBS-0147.pdf")

or from the command line:
    python src/extract_rfq.py data/raw/RFQ_KBS-0147.pdf

How it works (same idea for all three formats)
----------------------------------------------
1. Pull every TABLE out of the file as a plain list of rows.
2. In each table, find the HEADER row by looking for column names we know
   ("Description", "Part Code", "Qty", ...). Different customers name the
   columns differently, so each canonical field has several synonyms.
3. Every row under the header is one RFQ line. Clean the text and return
   one table with the same columns, whatever the file type was.
"""

import re
import sys
from pathlib import Path

import pandas as pd

# ------------------------------------------------------------ column names
# Canonical field -> the header texts customers might use for it.
# Headers are compared after lower-casing and removing everything except
# letters and digits, so "Part Code", "part-code" and "PART CODE" all match.
SYNONYMS = {
    "line_no": {"no", "sno", "srno", "slno", "item", "itemno", "sr", "serial", "pos", "position"},
    "description": {"description", "itemdescription", "details", "particulars", "materialdescription", "product"},
    "make": {"make", "brand", "manufacturer", "supplier", "mfr"},
    "part_code": {"partcode", "partno", "partnumber", "catno", "catalogueno", "catalognumber",
                  "ordercode", "orderingcode", "code", "reference", "modelno", "mlfb"},
    "qty": {"qty", "quantity", "qnty"},
    "unit": {"unit", "uom", "units", "unitofmeasure"},
}

OUTPUT_COLUMNS = [
    "line_no", "description", "make", "part_code", "code_note",
    "qty", "unit", "source",
]

# Words people write instead of a part code when they have none.
NO_CODE_WORDS = {"", "TBC", "TBA", "NA", "NIL", "NONE", "TOBECONFIRMED"}


# ------------------------------------------------------------ small helpers
def clean(cell) -> str:
    """Make a cell into tidy one-line text."""
    if cell is None:
        return ""
    text = str(cell).replace("-\n", "-")          # 'thermal-\nmagnetic'
    return re.sub(r"\s+", " ", text).strip()


def header_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", clean(text).lower())


def map_header(row):
    """If this row looks like a header, return {column_index: field}."""
    mapping = {}
    for index, cell in enumerate(row):
        key = header_key(cell)
        for field, names in SYNONYMS.items():
            if key in names and field not in mapping.values():
                mapping[index] = field
                break
    # A real header names the description plus at least two other fields.
    if "description" in mapping.values() and len(mapping) >= 3:
        return mapping
    return None


def split_code_note(cell):
    """Separate a real part code from explanatory notes."""
    text = clean(cell)

    # Extract text written inside brackets.
    notes = re.findall(r"\(([^)]*)\)", text)

    # Remove bracketed notes from the possible part code.
    code = re.sub(r"\([^)]*\)", "", text).strip()

    # Compare a simplified version of the text.
    key = header_key(code)

    # Recognise common ways of saying a code is missing.
    missing_code = (
        key in {"", "tbc", "tba", "na", "nil", "none", "tobeconfirmed"}
        or "tobeconfirmed" in key
        or (
            "supplier" in key
            and ("code" in key or "particular" in key)
        )
    )

    if missing_code:
        if text and not notes:
            notes.append(text)
        code = ""

    return code, "; ".join(note.strip() for note in notes)



def normalise_make(text: str) -> str:
    """Use the same supplier names as the price catalogue."""
    low = clean(text).lower()
    if "abb" in low:
        return "ABB"
    if "schneider" in low:
        return "Schneider Electric"
    if "siemens" in low:
        return "Siemens"
    if re.search(r"\blucy\b", low):
        return "Lucy Electric"
    return clean(text)


def to_number(text: str):
    match = re.search(r"\d+(?:\.\d+)?", clean(text).replace(",", ""))
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


# ------------------------------------------------------------ table -> lines
def lines_from_tables(tables):
    """tables: list of (location_text, rows). Returns a DataFrame of lines."""
    found = []
    last_mapping = None
    last_width = None

    for location, rows in tables:
        rows = [list(r) for r in rows if any(clean(c) for c in r)]
        if not rows:
            continue

        # Find the header row inside this table (could be below a title).
        mapping, start = None, 0
        for i, row in enumerate(rows[:30]):
            mapping = map_header(row)
            if mapping:
                start = i + 1
                break

        # A table that continues on the next page may not repeat its header.
        if mapping is None and last_mapping and len(rows[0]) == last_width:
            mapping, start = last_mapping, 0
        if mapping is None:
            continue
        last_mapping, last_width = mapping, len(rows[0])

        for row in rows[start:]:
            if map_header(row):          # repeated header row: skip
                continue
            values = {field: clean(row[i]) for i, field in mapping.items() if i < len(row)}
            # The part code cell needs special care (notes in brackets).
            code_cells = [row[i] for i, f in mapping.items() if f == "part_code" and i < len(row)]
            code, note = split_code_note(code_cells[0] if code_cells else "")

            line_no = values.get("line_no", "")
            description = values.get("description", "")
            qty = to_number(values.get("qty", ""))
            # Skip total / blank / note rows: a real line has a description
            # (or code) AND a line number or quantity.
            if not (description or code) or not (line_no or qty is not None):
                continue

            found.append(
                {
                    "line_no": line_no,
                    "description": description,
                    "make": normalise_make(values.get("make", "")),
                    "part_code": code,
                    "code_note": note,
                    "qty": qty,
                    "unit": values.get("unit", ""),
                    "source": location,
                }
            )

    return pd.DataFrame(found, columns=OUTPUT_COLUMNS)


# ------------------------------------------------------------ readers
def _has_header(rows) -> bool:
    return any(map_header(row) for row in list(rows)[:30])


def _words_as_boxes(page):
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    return [
        {"text": w["text"], "x0": w["x0"], "y0": w["top"], "x1": w["x1"], "y1": w["bottom"], "score": 1.0}
        for w in words
    ]


def _tidy_description_column(rows):
    from src.layout import tidy_ocr_text

    mapping = map_header(rows[0]) or {}
    for i, field in mapping.items():
        if field == "description":
            for row in rows[1:]:
                if i < len(row):
                    row[i] = tidy_ocr_text(row[i])
    return rows


def tables_from_pdf(path: Path):
    """Tables on every page. Three kinds of page are handled:
    * normal pages with ruled tables  -> pdfplumber's table finder,
    * tables without lines            -> rebuilt from word positions,
    * scanned pages (just an image)   -> OCR, then rebuilt from positions.
    """
    import pdfplumber
    from src import layout, ocr

    tables = []
    carry = {"ocr": (None, None), "words": (None, None)}  # header for continued tables
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if ocr.page_needs_ocr(page):
                boxes = ocr.ocr_pdf_page(path, number - 1)

                def reread(x0, y0, x1, y1, _page=number - 1):
                    return ocr.reread_region(path, _page, x0, y0, x1, y1)

                rows, cells, mapping, flagged = layout.table_from_boxes(
                    boxes, *carry["ocr"], reread=reread
                )
                carry["ocr"] = (cells, mapping)
                if rows:
                    location = f"page {number} (OCR)"
                    if flagged:
                        location += f" - check line {', '.join(flagged)}"
                    tables.append((location, _tidy_description_column(rows)))
                continue

            found = page.extract_tables()
            for t, rows in enumerate(found, start=1):
                tables.append((f"page {number}, table {t}", rows))
            if not any(_has_header(rows) for rows in found):
                boxes = layout.merge_words(_words_as_boxes(page))
                rows, cells, mapping, _ = layout.table_from_boxes(boxes, *carry["words"])
                carry["words"] = (cells, mapping)
                if rows:
                    tables.append((f"page {number}, text layout", rows))
    return tables


def label_rows_from_pdf(path: Path):
    """Rows used to find 'label | value' header details. Scanned pages add
    every OCR text row split into cells."""
    import pdfplumber
    from src import layout, ocr

    rows = [r for _, table in tables_from_pdf(path) for r in table]
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if ocr.page_needs_ocr(page):
                rows += layout.cell_rows(ocr.ocr_pdf_page(path, number - 1))
    return rows


def pdf_has_scanned_pages(path) -> bool:
    import pdfplumber
    from src import ocr

    with pdfplumber.open(path) as pdf:
        return any(ocr.page_needs_ocr(page) for page in pdf.pages)


def tables_from_docx(path: Path):
    import docx

    document = docx.Document(str(path))
    tables = []
    for t, table in enumerate(document.tables, start=1):
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        tables.append((f"table {t}", rows))
    return tables


def tables_from_excel(path: Path):
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    tables = []
    for sheet in workbook.worksheets:
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        tables.append((f"sheet '{sheet.title}'", rows))
    return tables


READERS = {
    ".pdf": tables_from_pdf,
    ".docx": tables_from_docx,
    ".xlsx": tables_from_excel,
    ".xlsm": tables_from_excel,
}


EMAIL_SUFFIXES = {".eml", ".msg", ".txt"}
SUPPORTED_TEXT = "PDF, DOCX, XLSX, EML, MSG or TXT"


class NoLineItemsError(ValueError):
    """The file was read but no RFQ line items were found in it."""


def _whole_numbers(lines: pd.DataFrame) -> pd.DataFrame:
    """Keep quantities as 24, not 24.0, even when one line has no quantity
    (pandas turns a number column with a gap into decimals)."""
    lines = lines.reset_index(drop=True)

    def tidy(value):
        if value is None or pd.isna(value):
            return None
        return int(value) if float(value).is_integer() else float(value)

    lines["qty"] = pd.Series([tidy(v) for v in lines["qty"]], dtype=object)
    return lines


def _lines_from_document(path: Path) -> pd.DataFrame:
    """Tables first; if there are none, read the items from the free text."""
    from src.parse_free_text import lines_from_text

    lines = lines_from_tables(READERS[path.suffix.lower()](path))
    if lines.empty:
        text = TEXT_READERS[path.suffix.lower()](path)
        lines = lines_from_text(text, "text")
    return lines


def _lines_from_email(path: Path) -> pd.DataFrame:
    from tempfile import TemporaryDirectory

    from src.parse_free_text import lines_from_text
    from src.read_email import read_email

    mail = read_email(path)
    parts = []
    with TemporaryDirectory() as folder:
        for filename, data in mail["attachments"]:
            suffix = Path(filename).suffix.lower()
            if suffix not in READERS or not data:
                continue
            attached = Path(folder) / filename
            attached.write_bytes(data)
            try:
                found = _lines_from_document(attached)
            except Exception:           # a broken attachment must not stop the email
                continue
            found["source"] = f"attachment {filename}, " + found["source"]
            parts.append(found)

    # Items in the email text itself. If an attachment holds a proper table
    # and the body only says 'please quote', the body adds nothing.
    body = lines_from_text(mail["body"], "email body")
    if not body.empty:
        parts.insert(0, body)
    if not parts:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    return pd.concat(parts, ignore_index=True)[OUTPUT_COLUMNS]


def extract_rfq_lines(path) -> pd.DataFrame:
    """Return the RFQ's line items as a table (one row per RFQ line).

    Order of attempts: tables (PDF/Word/Excel) -> OCR for scanned PDF pages
    -> table layout rebuilt from text positions -> free text (emails, plain
    text, prose RFQs). The 'source' column says which one found each line.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in EMAIL_SUFFIXES:
        lines = _lines_from_email(path)
    elif suffix in READERS:
        lines = _lines_from_document(path)
    else:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Use {SUPPORTED_TEXT}.")
    if lines.empty:
        raise NoLineItemsError(
            f"No line items found in {path.name}. There was no item table, and "
            "the text has no lines with a quantity (e.g. '10 nos') or a "
            "numbered item list."
        )
    return _whole_numbers(lines)


def extract_rfq_from_text(text: str):
    """Line items and header from pasted text (e.g. an email body).
    Returns (lines DataFrame, header dict)."""
    from src.parse_free_text import lines_from_text
    from src.read_email import header_from_text

    lines = lines_from_text(text or "", "pasted text")
    if lines.empty:
        raise NoLineItemsError(
            "No line items found in the pasted text. Put one item per line with "
            "its quantity (e.g. 'ABB MCB 32A 4P - 10 nos'), or paste the item table."
        )
    return _whole_numbers(lines), header_from_text(text or "")


# ------------------------------------------------------------ RFQ header
# The details around the line items: who is asking, the RFQ number, dates...
# Every field can come back empty ("") - a person fills the gaps in the app.
HEADER_FIELDS = [
    ("customer_name", "Customer name"),
    ("address", "Customer address"),
    ("phone", "Phone"),
    ("email", "Email"),
    ("contact_person", "Contact person"),
    ("rfq_number", "RFQ number"),
    ("rfq_date", "RFQ date"),
    ("due_date", "Quote due by"),
    ("project", "Project"),
    ("currency", "Currency requested"),
]

# Label text (after header_key cleaning) -> header field. Used on rows that
# look like "label | value", e.g. "RFQ No. | KBS/RFQ/2026/0147".
LABEL_SYNONYMS = {
    "rfq_number": {"rfqno", "rfqnumber", "rfqref", "rfqreference", "enquiryno",
                   "enquiryref", "inquiryno", "inquiryref", "referenceno",
                   "reference", "refno"},
    "rfq_date": {"date", "issuedate", "rfqdate", "dateofissue", "dateissued"},
    "due_date": {"quoteby", "quotedueby", "quoteduedate", "quotationdue",
                 "duedate", "dueby", "closingdate", "submissiondeadline",
                 "deadline", "submissiondate"},
    "project": {"project", "projectname", "subject", "title", "projecttitle"},
    "contact_person": {"contact", "contactperson", "attention", "attn",
                       "kindattention"},
}

# The first line that looks like the document title ends the letterhead.
TITLE_RE = re.compile(
    r"request\s*for\s*(?:quotation|quote|price|proposal)|\brfq\b|\benquiry\b|\binquiry\b",
    re.I,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RES = [
    re.compile(r"\b(?:tel(?:ephone)?|phone|ph|mob(?:ile)?)\b\.?\s*(?:no\.?)?\s*[:\-]?\s*(\+?\d[\d\s()\-]{6,}\d)", re.I),
    re.compile(r"\bT\s*:\s*(\+?\d[\d\s()\-]{6,}\d)"),
]
CONTACT_LINE_RE = re.compile(
    r"@|https?://|\b(?:tel|telephone|phone|ph|mob|mobile|fax|email|e-mail|www)\b", re.I
)
# No \b on the left: OCR often glues words ("inGBP").
CURRENCY_RE = re.compile(r"(?<![A-Z])(GBP|USD|EUR|INR|AED|CAD|AUD)\b")
CURRENCY_SYMBOLS = {"£": "GBP", "€": "EUR", "₹": "INR"}


def text_lines_from_pdf(path: Path):
    import pdfplumber
    from src import layout, ocr

    lines = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if ocr.page_needs_ocr(page):
                lines += layout.text_lines(ocr.ocr_pdf_page(path, number - 1))
            else:
                lines += (page.extract_text() or "").splitlines()
    return lines


def text_lines_from_docx(path: Path):
    import docx

    document = docx.Document(str(path))
    lines = []
    for section in document.sections:          # letterheads often sit here
        lines += [p.text for p in section.header.paragraphs]
    lines += [p.text for p in document.paragraphs]
    return lines


def text_lines_from_excel(path: Path):
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    lines = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [clean(c) for c in row if clean(c)]
            if cells:
                lines.append("  ".join(cells))
    return lines


TEXT_READERS = {
    ".pdf": text_lines_from_pdf,
    ".docx": text_lines_from_docx,
    ".xlsx": text_lines_from_excel,
    ".xlsm": text_lines_from_excel,
}


def parse_letterhead(lines):
    """Customer name, address, phone and email from the lines above the title."""
    lines = [clean(line) for line in lines if clean(line)]
    cut = next((i for i, line in enumerate(lines) if TITLE_RE.search(line)), min(len(lines), 8))
    top = lines[:cut]
    text = " ".join(top)

    name, address_parts = "", []
    for line in top:
        # Two-column letterheads put 'Name   T : +44...' on one line: keep
        # only the part before the contact marker.
        line = re.split(
            r"\s+(?:T|Tel|Telephone|Phone|Ph|Mob|Mobile|Fax|E|Email|E-mail|W|Web)\s*:",
            line, maxsplit=1, flags=re.I,
        )[0].strip()
        if CONTACT_LINE_RE.search(line) or not re.search(r"[A-Za-z]", line):
            continue
        if not name:
            name = line
        else:
            address_parts.append(line)

    email = EMAIL_RE.search(text)
    phone = ""
    for pattern in PHONE_RES:
        match = pattern.search(text)
        if match:
            phone = clean(match.group(1))
            break

    return {
        "customer_name": name,
        "address": ", ".join(address_parts),
        "phone": phone,
        "email": email.group(0) if email else "",
    }


def tidy_date(text: str) -> str:
    """'15 October 2026' -> '15/10/2026'. Anything unclear is kept as written."""
    if not text:
        return ""
    # OCR can glue words: '15 October2026' -> '15 October 2026'.
    text = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z]{3,})", " ", text)
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", text):
            return pd.to_datetime(text[:10], format="%Y-%m-%d").strftime("%d/%m/%Y")
        return pd.to_datetime(text, dayfirst=True).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return text


def extract_rfq_header(path) -> dict:
    """Return the RFQ's header details as a dict (empty string if not found)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in EMAIL_SUFFIXES:
        return _header_from_email(path)
    if suffix not in READERS or suffix not in TEXT_READERS:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Use {SUPPORTED_TEXT}.")

    header = {key: "" for key, _ in HEADER_FIELDS}
    lines = TEXT_READERS[suffix](path)
    header.update(parse_letterhead(lines))

    # 'Label | value' rows anywhere in the file (RFQ No., Date, Project...).
    if suffix == ".pdf":
        label_rows = label_rows_from_pdf(path)
    else:
        label_rows = [r for _, rows in READERS[suffix](path) for r in rows]
    for row in label_rows:
        cells = [clean(c) for c in row if clean(c)]
        if len(cells) < 2:
            continue
        key = header_key(cells[0])
        for field, names in LABEL_SYNONYMS.items():
            if key in names and not header[field]:
                header[field] = cells[1]

    header["rfq_date"] = tidy_date(header["rfq_date"])

    # Currency: the first ISO code mentioned, else a currency symbol.
    full_text = " ".join(lines)
    match = CURRENCY_RE.search(full_text)
    if match:
        header["currency"] = match.group(1)
    else:
        header["currency"] = next(
            (code for symbol, code in CURRENCY_SYMBOLS.items() if symbol in full_text), ""
        )
    return header


def _header_from_email(path: Path) -> dict:
    """Header from the email itself; gaps are filled from an attached RFQ."""
    from tempfile import TemporaryDirectory

    from src.read_email import header_from_mail, read_email

    mail = read_email(path)
    header = header_from_mail(mail)
    with TemporaryDirectory() as folder:
        for filename, data in mail["attachments"]:
            if Path(filename).suffix.lower() not in READERS or not data:
                continue
            attached = Path(folder) / filename
            attached.write_bytes(data)
            try:
                from_file = extract_rfq_header(attached)
            except Exception:
                continue
            for key, value in from_file.items():
                # The attached RFQ document is more formal than the email for
                # these fields; for the rest the email wins.
                if value and (not header[key] or key in ("customer_name", "address", "rfq_number")):
                    header[key] = value
    return header


if __name__ == "__main__":
    # Allow 'python src/extract_rfq.py file' as well as 'python -m src.extract_rfq'.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    if len(sys.argv) != 2:
        sys.exit("Usage: python src/extract_rfq.py <rfq file>")
    result = extract_rfq_lines(sys.argv[1])
    header = extract_rfq_header(sys.argv[1])
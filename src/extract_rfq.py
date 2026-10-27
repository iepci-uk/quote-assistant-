"""Read an RFQ file (PDF, Word or Excel) and return its line items.

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
def tables_from_pdf(path: Path):
    import pdfplumber

    tables = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            for t, rows in enumerate(page.extract_tables(), start=1):
                tables.append((f"page {number}, table {t}", rows))
    return tables


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


def extract_rfq_lines(path) -> pd.DataFrame:
    """Return the RFQ's line items as a table (one row per RFQ line)."""
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(
            f"Unsupported file type '{path.suffix}'. Use PDF, DOCX or XLSX."
        )
    lines = lines_from_tables(reader(path))
    if lines.empty:
        raise ValueError(
            f"No line-item table found in {path.name}. If this is a scanned "
            "PDF it needs OCR first; if the items are in an email or plain "
            "text, they need the AI extraction step (not built yet)."
        )
    return lines


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
    r"request\s+for\s+(?:quotation|quote|price|proposal)|\brfq\b|\benquiry\b|\binquiry\b",
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
CURRENCY_RE = re.compile(r"\b(GBP|USD|EUR|INR|AED|CAD|AUD)\b")
CURRENCY_SYMBOLS = {"£": "GBP", "€": "EUR", "₹": "INR"}


def text_lines_from_pdf(path: Path):
    import pdfplumber

    lines = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
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
    if suffix not in READERS or suffix not in TEXT_READERS:
        raise ValueError(f"Unsupported file type '{path.suffix}'. Use PDF, DOCX or XLSX.")

    header = {key: "" for key, _ in HEADER_FIELDS}
    lines = TEXT_READERS[suffix](path)
    header.update(parse_letterhead(lines))

    # 'Label | value' rows anywhere in the file (RFQ No., Date, Project...).
    for _, rows in READERS[suffix](path):
        for row in rows:
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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python src/extract_rfq.py <rfq file>")
    result = extract_rfq_lines(sys.argv[1])
    pd.set_option("display.width", 200, "display.max_colwidth", 38)
    print(result.drop(columns=["source"]).to_string(index=False))
    print(f"\n{len(result)} lines extracted.")
    header = extract_rfq_header(sys.argv[1])
    print("\nRFQ header:")
    for key, label in HEADER_FIELDS:
        print(f"  {label}: {header[key] or '-'}")
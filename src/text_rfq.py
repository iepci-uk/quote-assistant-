"""Read RFQs written as text: pasted email text, .txt, .eml and .msg files.

    from src.text_rfq import lines_from_text, header_from_text
    lines = lines_from_text(email_body)

How it works
------------
Emails with an attached RFQ (PDF, Word, Excel, scan) are read from the
attachment, exactly like an uploaded file. Otherwise the email text is read
in three ways, and the first that finds items is used:

1. A table pasted into the email (columns split by tabs, '|' or wide gaps).
   Its header row is found with the same column names as file tables.
2. Items written as labelled blocks:
       Description: MCCB 100 A 3 pole
       Part No: LV510347
       Qty: 4
3. One item per line, for example:
       1. ABB S203-C16 MCB 3 pole 16 A - 10 nos
       - LV429387 shunt trip, qty 6
   Line number, quantity (with its unit), make and part code are picked out;
   the rest of the line is the description.

Nothing is guessed: a line with two possible quantities gets no quantity and
the note "check qty"; a part code that is not in the price lists is kept as
typed (the code check then sends it to a person).
"""

import email
import re
from email import policy
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.extract_rfq import (
    CURRENCY_RE, CURRENCY_SYMBOLS, EMAIL_RE, HEADER_FIELDS, LABEL_SYNONYMS, OUTPUT_COLUMNS,
    PHONE_RES, SYNONYMS, clean, header_key, lines_from_tables, normalise_make,
    split_code_note, tidy_date, to_number,
)
from src.load_price_lists import make_key

# ------------------------------------------------------------ patterns
UNITS = {
    "no": "No", "nos": "Nos", "no.": "No", "nos.": "Nos", "number": "Nos", "numbers": "Nos",
    "pc": "Pcs", "pcs": "Pcs", "pc.": "Pcs", "pcs.": "Pcs", "piece": "Pcs", "pieces": "Pcs",
    "unit": "Units", "units": "Units", "set": "Sets", "sets": "Sets", "ea": "Ea", "each": "Ea",
    "pair": "Pairs", "pairs": "Pairs", "lot": "Lot", "lots": "Lot", "box": "Box", "boxes": "Box",
    "m": "m", "mtr": "m", "mtrs": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "roll": "Rolls", "rolls": "Rolls", "pkt": "Pkt", "pkts": "Pkt",
}
UNIT_WORDS = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
NUMBER = r"\d+(?:\.\d+)?"

# Each pattern: group 1 = the quantity, group 2 (if any) = its unit.
QTY_PATTERNS = [
    # 'qty: 10', 'quantity 10 nos'
    re.compile(rf"\b(?:qty|quantity|qnty)\.?\s*[:=\-]?\s*({NUMBER})(?:\s*({UNIT_WORDS})(?!\w))?", re.I),
    # '10 nos', '10nos', '6 pcs.'
    re.compile(rf"(?<![\w.])({NUMBER})\s*({UNIT_WORDS})(?!\w)", re.I),
    # '10 x MCB ...', '2 off MCB ...' at the start of the item
    re.compile(rf"^\s*({NUMBER})\s*(?:x|×|off|nos?\.?\s+of)\s+(?=[A-Za-z])", re.I),
    # '... MCB x 10' at the end
    re.compile(rf"\s(?:x|×)\s*({NUMBER})\s*$", re.I),
]

ITEM_START = re.compile(r"^\s*(?:item\s*)?(?:no\.?\s*)?(\d{1,3})\s*[.):\-]\s+(?=\S)", re.I)
BULLET = re.compile(r"^\s*[-*•·▪►]\s+(?=\S)")
CODE_LABEL = re.compile(
    r"\b(?:part\s*(?:no|number|code)|cat(?:alogue|alog)?\.?\s*(?:no|number)|order(?:ing)?\s*code|"
    r"p/n|code|ref(?:erence)?|model\s*no)\.?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9 \-/.]*[A-Z0-9])",
    re.I,
)
MISSING_CODE = re.compile(
    r"(?:\(?\s*(?:part\s*(?:no|number|code)|code)\.?\s*[:\-]?\s*)?"
    r"(?:to\s+be\s+confirmed(?:\s+by\s+(?:the\s+)?supplier)?|tbc|tba|not\s+known|unknown)\b\s*\)?",
    re.I,
)
REQUEST_WORDS = re.compile(
    r"^(?:(?:please|pls|plz|kindly)\s+)?(?:quote|send\s+(?:your\s+)?(?:best\s+)?(?:price|offer)|"
    r"need|require|required|supply)\s*(?:for|of)?\s*[:\-]?\s*",
    re.I,
)
MAKE_WORDS = re.compile(r"\b(ABB|Schneider(?:\s+Electric)?)\b", re.I)

CLOSING = re.compile(
    r"^\s*(?:thanks|thank\s+you|regards|best\s+regards|kind\s+regards|warm\s+regards|"
    r"yours\s+(?:sincerely|faithfully|truly)|sincerely|cheers|br,?)\b",
    re.I,
)
HEADER_LINE = re.compile(r"^\s*(?:from|to|cc|bcc|sent|date|subject)\s*:", re.I)
QUOTED_HISTORY = re.compile(r"^\s*(?:-{2,}\s*original message|on .+ wrote:\s*$)", re.I)


# ------------------------------------------------------------ helpers
def text_lines(text: str):
    """Email text -> lines, with '>' reply markers removed."""
    return [re.sub(r"^(?:\s*>)+\s?", "", line).rstrip() for line in text.replace("\r\n", "\n").split("\n")]


def body_lines(text: str):
    """Lines of the request itself: stops at the sign-off or quoted history."""
    lines = []
    for line in text_lines(text):
        if CLOSING.match(line) or QUOTED_HISTORY.match(line):
            break
        lines.append(line)
    return lines


def make_of(text: str) -> str:
    makes = {normalise_make(m) for m in MAKE_WORDS.findall(text)}
    return makes.pop() if len(makes) == 1 else ""


# ------------------------------------------------------------ 1. pasted table
def split_columns(line: str):
    if "\t" in line:
        return [cell.strip() for cell in line.split("\t")]
    if line.count("|") >= 2:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]
    return [cell.strip() for cell in re.split(r"\s{2,}", line.strip())]


def lines_from_pasted_table(lines):
    rows = []
    for line in lines:
        cells = split_columns(line)
        if all(re.fullmatch(r"[-=:+\s]*", cell) for cell in cells):
            continue                                   # |----|----| separator rows
        rows.append(cells)
    return lines_from_tables([("email table", rows)])


# ------------------------------------------------------------ 2. labelled blocks
LABEL_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z ./#]{0,25}?)\s*[:=\-]\s*(.+)$")


def field_of_label(label: str):
    key = header_key(label)
    for name, names in SYNONYMS.items():
        if key in names:
            return name
    return None


def lines_from_blocks(lines):
    items, current = [], {}

    def finish():
        if current.get("description") or current.get("part_code"):
            items.append(dict(current))
        current.clear()

    for number, line in enumerate(lines, start=1):
        match = LABEL_LINE.match(line)
        name = field_of_label(match.group(1)) if match else None
        if not name:
            if not line.strip() and current:
                finish()
            continue
        if name in current:                      # same label again: next item
            finish()
        current[name] = clean(match.group(2))
        current.setdefault("_line", number)
    finish()

    found = []
    for n, item in enumerate(items, start=1):
        code, note = split_code_note(item.get("part_code", ""))
        qty = to_number(item.get("qty", ""))
        unit = item.get("unit", "") or find_qty(item.get("qty", ""))[1]
        if qty is None:
            continue
        found.append({
            "line_no": re.sub(r"\D", "", item.get("line_no", "")) or str(n),
            "description": item.get("description", ""),
            "make": normalise_make(item["make"]) if item.get("make") else make_of(item.get("description", "")),
            "part_code": code,
            "code_note": note,
            "qty": qty,
            "unit": unit,
            "source": f"email line {item['_line']}",
        })
    return pd.DataFrame(found, columns=OUTPUT_COLUMNS)


# ------------------------------------------------------------ 3. one item per line
CODE_SHAPE = re.compile(r"^(?=.*\d)(?=.*[A-Z])[A-Z0-9][A-Z0-9\-/.]{4,}[A-Z0-9]$")


def find_code(text: str, index):
    """(code, start, end) of the part code in a line, or ('', -1, -1)."""
    tokens = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9\-/.]*", text)]

    label = CODE_LABEL.search(text)
    if label:
        # 'Part No: 1SDA 066799 R1 - 4 nos': the code may hold spaces. Take the
        # longest run of words that is a catalogue code, else the code-like words.
        after = [t for t in tokens if t[1] >= label.start(1)][:4]
        size = 0
        if index:
            size = next((n for n in range(len(after), 0, -1)
                         if index.knows(make_key(" ".join(t for t, _, _ in after[:n])))), 0)
        if not size:
            size = 1
            while size < len(after) and re.fullmatch(r"[A-Z0-9\-/.]{2,}", after[size][0]) \
                    and re.search(r"\d", after[size][0]):
                size += 1
        if after:
            return " ".join(t for t, _, _ in after[:size]), label.start(), after[size - 1][2]

    # A catalogue code, possibly typed with spaces ('1SDA 066799 R1'): longest first.
    if index:
        for size in (3, 2, 1):
            for i in range(len(tokens) - size + 1):
                group = tokens[i:i + size]
                key = make_key(" ".join(t for t, _, _ in group))
                if len(key) >= 5 and index.knows(key):
                    return " ".join(t for t, _, _ in group), group[0][1], group[-1][2]
    # Otherwise something that looks like a code: capitals and 3+ digits, 6+ long.
    for token, start, end in tokens:
        if CODE_SHAPE.match(token) and len(re.sub(r"\D", "", token)) >= 3:
            return token, start, end
    return "", -1, -1


def find_qty(text: str):
    """(qty, unit, [(start, end) of each match], ambiguous).

    If the text gives two different quantities, none is chosen (ambiguous).
    """
    found = []
    for pattern in QTY_PATTERNS:
        for match in pattern.finditer(text):
            unit = match.group(2) if pattern.groups >= 2 else None
            if unit == "M":
                continue                      # 'SB200 M series' is not 200 metres
            found.append((to_number(match.group(1)), UNITS.get((unit or "").lower(), ""), match.start(), match.end()))
    if not found:
        return None, "", [], False
    if len({value for value, _, _, _ in found}) > 1:
        return None, "", [], True
    unit = next((u for _, u, _, _ in found if u), "")
    return found[0][0], unit, [(s, e) for _, _, s, e in found], False


def lines_from_item_lines(lines, index=None):
    found, current_make, previous = [], "", None
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            previous = None
            continue
        if HEADER_LINE.match(line) or EMAIL_RE.search(line) or re.search(r"https?://|www\.", line):
            previous = None
            continue

        start = ITEM_START.match(line)
        bullet = BULLET.match(line)
        rest = line[(start or bullet).end():] if (start or bullet) else line

        missing = MISSING_CODE.search(rest)
        missing_note = ""
        if missing:
            missing_note = clean(missing.group(0)).strip("() ")
            rest = rest[:missing.start()] + " " + rest[missing.end():]
        code, code_start, code_end = find_code(rest, index)
        # Look for the quantity with the code blanked out, so its digits don't count.
        without_code = rest[:code_start] + " " * (code_end - code_start) + rest[code_end:] if code else rest
        qty, unit, qty_spans, unclear_qty = find_qty(without_code)
        make = make_of(rest)

        if start or bullet:
            is_item = bool(code or missing) or qty is not None or unclear_qty
        else:
            # Unnumbered lines must look clearly like an item, not a sentence
            # ('We need 2 sets of drawings'): a code, a make, or the quantity
            # at the very start or end of the line.
            at_edge = any(s <= 1 or e >= len(without_code.rstrip()) - 1 for s, e in qty_spans)
            is_item = bool(code) or (qty is not None and (make or at_edge))
        if not is_item:
            # A wrapped item: the next line continues its description.
            if previous is not None and not (start or bullet) and line.startswith((" ", "\t")):
                previous["description"] = clean(f"{previous['description']} {line}")
                continue
            if make and not (start or bullet):
                current_make = make                    # 'ABB items:' heading
            previous = None
            continue

        description = rest
        cut = sorted(qty_spans + ([(code_start, code_end)] if code else []), reverse=True)
        for s, e in cut:
            description = description[:s] + " " + description[e:]
        description = re.sub(r"\b(?:qty|quantity|part\s*no|p/n|code)\b\.?\s*[:#\-]?", " ", description, flags=re.I)
        description = clean(re.sub(r"\s*[,;:\-–]\s*(?=[,;:\-–]|$)", "", description)).strip(" ,;:-–")
        description = REQUEST_WORDS.sub("", description).strip(" ,;:-–")
        description = re.sub(r"\s+([,;])", r"\1", re.sub(r"([,;])\s*(?=[,;])", "", description))

        code, note = split_code_note(code)
        notes = [n for n in (note, missing_note) if n]
        if unclear_qty:
            notes.append("check qty")
        item = {
            "line_no": start.group(1) if start else str(len(found) + 1),
            "description": description,
            "make": make or current_make,
            "part_code": code,
            "code_note": "; ".join(notes),
            "qty": qty,
            "unit": unit,
            "source": f"email line {number}",
        }
        found.append(item)
        previous = item
    return pd.DataFrame(found, columns=OUTPUT_COLUMNS)


# ------------------------------------------------------------ text -> lines
def lines_from_text(text: str, catalogue=None) -> pd.DataFrame:
    """Line items from email / plain text. Raises ValueError if none found."""
    from src.code_correction import correct_codes
    from src.extract_rfq import code_index

    lines = body_lines(text)
    index = code_index(catalogue)
    for reader in (lines_from_pasted_table, lines_from_blocks):
        found = reader(lines)
        if not found.empty:
            break
    else:
        found = lines_from_item_lines(lines, index)
    if found.empty:
        raise ValueError(
            "No RFQ items were recognised in the text. Write one item per line "
            "with its quantity (for example '1. MCCB 100 A 3 pole, LV510347 - 4 nos'), "
            "or paste the items as a table with a header row."
        )
    if index is not None:
        found = correct_codes(found, index, typed=True)
        found = fill_make_from_code(found, index)
    return found.reset_index(drop=True)


def fill_make_from_code(lines, index):
    """No make given, but the code is in only one supplier's list: use that supplier."""
    lines = lines.copy()
    for i, line in lines.iterrows():
        key = make_key(line["part_code"])
        if line["make"] or not key:
            continue
        suppliers = [s for s in index.by_supplier if key in index.by_supplier[s]]
        if len(suppliers) == 1:
            lines.at[i, "make"] = suppliers[0]
    return lines


# ------------------------------------------------------------ text -> header
RFQ_NUMBER = re.compile(
    r"\b(?:rfq|rfp|enquiry|inquiry|ref(?:erence)?)\.?\s*(?:no\.?|number|#|ref\.?)?\s*[:#\-]?\s*"
    r"([A-Z0-9][A-Z0-9/\-_.]*\d[A-Z0-9/\-_]*)",
    re.I,
)
DATE = (
    r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|"
    r"[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2}"
)
DUE = re.compile(
    rf"\b(?:by|before|latest\s+by|no\s+later\s+than|due(?:\s+date)?|deadline|closing\s+date|on\s+or\s+before)"
    rf"\s*[:\-]?\s*(?:[A-Za-z]+day,?\s+)?({DATE})",
    re.I,
)
COMPANY = re.compile(
    r"\b(?:ltd|limited|pvt|llp|llc|inc|gmbh|plc|co\.|company|corporation|industries|engineering|"
    r"services|electricals?|enterprises|group|solutions|contractors|projects|systems)\b\.?",
    re.I,
)


def signature_lines(text: str):
    """Lines after the sign-off ('Regards,' ...), up to quoted history."""
    lines = text_lines(text)
    for i, line in enumerate(lines):
        if CLOSING.match(line):
            tail = []
            for following in lines[i + 1:]:
                if QUOTED_HISTORY.match(following) or HEADER_LINE.match(following):
                    break
                tail.append(clean(following))
            return [line for line in tail if line][:8]
    return []


def header_from_text(text: str, meta: dict = None) -> dict:
    """RFQ header details from email text and its From / Subject / Date."""
    meta = meta or {}
    header = {key: "" for key, _ in HEADER_FIELDS}
    lines = [clean(line) for line in text_lines(text)]
    full = " ".join(lines)
    signature = signature_lines(text)
    sig_text = " ".join(signature)

    # 'Label: value' lines, as in file RFQs (RFQ No.:, Project:, Contact:).
    for line in lines:
        match = LABEL_LINE.match(line)
        if not match:
            continue
        key = header_key(match.group(1))
        for name, names in LABEL_SYNONYMS.items():
            if key in names and not header[name]:
                # 'RFQ No: KBS/0200. Kindly quote by ...': the value ends with its sentence.
                value = re.split(r"\.\s+(?=[A-Z])", clean(match.group(2)))[0]
                header[name] = value.split()[0].rstrip(".,;") if name == "rfq_number" else value

    subject = re.sub(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)+", "", meta.get("subject", ""), flags=re.I)
    if not header["rfq_number"]:
        match = RFQ_NUMBER.search(subject) or RFQ_NUMBER.search(full)
        header["rfq_number"] = match.group(1).rstrip(".") if match else ""
    if not header["project"] and subject:
        # 'RFQ ACM/2026/77 - Substation LV panel' -> 'Substation LV panel'
        project = RFQ_NUMBER.sub("", subject)
        project = re.sub(r"^\W*(?:request\s+for\s+(?:quotation|quote)|quotation|rfq)\b\W*", "", project, flags=re.I)
        header["project"] = clean(project).strip(" -–:,") or subject

    if not header["rfq_date"] and meta.get("date"):
        header["rfq_date"] = meta["date"]
    header["rfq_date"] = tidy_date(header["rfq_date"])
    if not header["due_date"]:
        match = DUE.search(full)
        header["due_date"] = match.group(1) if match else ""

    sender_name, sender_email = meta.get("from_name", ""), meta.get("from_email", "")
    email_match = EMAIL_RE.search(sig_text)
    header["email"] = sender_email or (email_match.group(0) if email_match else "")
    for pattern in PHONE_RES:
        match = pattern.search(sig_text) or pattern.search(full)
        if match:
            header["phone"] = clean(match.group(1))
            break

    plain = [line for line in signature if not EMAIL_RE.search(line) and not re.search(r"\d{5,}|https?://|www\.", line)]
    if not header["contact_person"]:
        header["contact_person"] = sender_name or (plain[0] if plain else "")
    company = next((line for line in plain if COMPANY.search(line)), "")
    header["customer_name"] = company
    if company:
        after = plain[plain.index(company) + 1:]
        header["address"] = ", ".join(line for line in after if not re.match(r"(?i)^(tel|phone|mob|fax|e-?mail|web)\b", line))

    match = CURRENCY_RE.search(full)
    header["currency"] = match.group(1) if match else next(
        (code for symbol, code in CURRENCY_SYMBOLS.items() if symbol in full), ""
    )
    return header


# ------------------------------------------------------------ email files
def read_message(path: Path):
    """(body text, meta, attachments [(filename, bytes)]) of a .txt/.eml/.msg."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        raw = path.read_bytes()
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding), {}, []
            except UnicodeDecodeError:
                continue
    if suffix == ".eml":
        return read_eml(path.read_bytes())
    if suffix == ".msg":
        return read_msg(path)
    raise ValueError(f"Unsupported email type '{path.suffix}'.")


def html_to_text(html: str) -> str:
    """HTML email -> text. Tables become tab-separated rows."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [clean(cell.get_text(" ")) for cell in tr.find_all(["td", "th"])]
            rows.append("\t".join(cells))
        table.replace_with("\n" + "\n".join(rows) + "\n")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3"]):
        block.insert_after("\n")
    return re.sub(r"\n{3,}", "\n\n", soup.get_text())


def read_eml(raw: bytes):
    from email.utils import parseaddr

    message = email.message_from_bytes(raw, policy=policy.default)
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    # An HTML part keeps tables as tables, so it wins when it has one.
    if html is not None and "<table" in html.get_content().lower():
        body = html_to_text(html.get_content())
    elif plain is not None:
        body = plain.get_content()
    elif html is not None:
        body = html_to_text(html.get_content())
    else:
        body = ""
    name, address = parseaddr(message.get("From", ""))
    meta = {"from_name": name, "from_email": address,
            "subject": message.get("Subject", ""), "date": email_date(message.get("Date", ""))}
    attachments = [(part.get_filename(), part.get_content()) for part in message.iter_attachments()
                   if part.get_filename()]
    return body, meta, [(n, c if isinstance(c, bytes) else str(c).encode()) for n, c in attachments]


def read_msg(path: Path):
    import extract_msg
    from email.utils import parseaddr

    message = extract_msg.openMsg(str(path))
    try:
        html = message.htmlBody
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        if html and "<table" in html.lower():
            body = html_to_text(html)
        else:
            body = message.body or (html_to_text(html) if html else "")
        name, address = parseaddr(message.sender or "")
        meta = {"from_name": name, "from_email": address, "subject": message.subject or "",
                "date": message.date.strftime("%Y-%m-%d") if message.date else ""}
        attachments = [(a.longFilename or a.shortFilename, a.data) for a in message.attachments
                       if isinstance(getattr(a, "data", None), bytes)]
    finally:
        message.close()
    return body, meta, attachments


def email_date(text: str) -> str:
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def from_attachments(attachments, catalogue):
    """(lines, header) from the first attachment that is a readable RFQ, else None."""
    from src.extract_rfq import READERS, extract_rfq_header, extract_rfq_lines

    with TemporaryDirectory() as folder:
        for name, data in attachments:
            target = Path(folder) / Path(name).name
            if target.suffix.lower() not in READERS:
                continue
            target.write_bytes(data)
            try:
                lines = extract_rfq_lines(target, catalogue)
            except ValueError:
                continue
            try:
                header = extract_rfq_header(target)
            except Exception:
                header = {key: "" for key, _ in HEADER_FIELDS}
            lines["source"] = f"{target.name}: " + lines["source"]
            return lines, header
    return None


def read_email_rfq(path, catalogue=None):
    """(lines, header) of an email / text RFQ file."""
    body, meta, attachments = read_message(Path(path))
    email_header = header_from_text(body, meta)
    attached = from_attachments(attachments, catalogue)
    if attached:
        lines, header = attached
        # The attached RFQ's own details first; the email fills the gaps.
        return lines, {key: header.get(key) or email_header[key] for key, _ in HEADER_FIELDS}
    return lines_from_text(body, catalogue), email_header


def lines_from_message(path, catalogue=None) -> pd.DataFrame:
    return read_email_rfq(path, catalogue)[0]


def header_from_message(path) -> dict:
    body, meta, attachments = read_message(Path(path))
    email_header = header_from_text(body, meta)
    attached = from_attachments(attachments, None) if attachments else None
    if attached:
        return {key: attached[1].get(key) or email_header[key] for key, _ in HEADER_FIELDS}
    return email_header

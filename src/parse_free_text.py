"""Find RFQ line items in free text: email bodies, pasted text, PDFs or scans
that have no table. Rule based - no AI service, no internet.

    from src.parse_free_text import lines_from_text
    lines = lines_from_text(email_body.splitlines(), "email body")

Understands the usual ways people write an enquiry:
  * a table pasted into the email (columns split by tabs, '|' or 2+ spaces),
  * labelled blocks:   Description: MCB 32A 4P / Make: ABB / Qty: 10 nos,
  * one item a line:   1. ABB MCB 32A 4P, 1SDA067049R1 - 10 nos
                       5 x Schneider LV429630 MCCB 100A
                       Contactor 26A, coil 230V AC   Qty: 8
Lines that are not items (greetings, delivery terms, signatures) are skipped
because they carry no quantity or product details. Every line found can be
edited in the app before quoting.
"""

import re

import pandas as pd

from src.extract_rfq import (
    OUTPUT_COLUMNS,
    SYNONYMS,
    clean,
    header_key,
    lines_from_tables,
    map_header,
    normalise_make,
    split_code_note,
    to_number,
)

# ------------------------------------------------------------ vocabulary
UNITS = (
    r"nos|no|numbers?|pcs|pc|pieces?|units?|sets?|ea|each|mtrs?|meters?|metres?|"
    r"m|rmt|rolls?|lots?|pairs?|prs|boxes|box|kits?|lengths?|coils?|drums?|lot|off"
)
_NUM = r"\d+(?:[.,]\d+)?"
QTY_LABEL_RE = re.compile(rf"\b(?:qty|quantity|qnty|qnt)\b\.?\s*[:=\-]?\s*({_NUM})\s*({UNITS})?\b\.?", re.I)
# "5 x ABB MCB" (a word must follow, so "4 x 2.5 sqmm" is not a quantity)
QTY_TIMES_START_RE = re.compile(rf"(?<![\w.,/-])({_NUM})\s*(?:{UNITS})?\s*[x×*]\s+(?=[A-Za-z])", re.I)
QTY_TIMES_END_RE = re.compile(rf"\s[x×*]\s*({_NUM})\s*({UNITS})?\.?\s*$", re.I)
QTY_UNIT_RE = re.compile(rf"(?<![\w./-])({_NUM})\s*({UNITS})\b\.?(?![\w/-])", re.I)

LIST_PREFIX_RE = re.compile(
    r"^\s*(?:(?:item|line|sl|sr|s)\.?\s*(?:no\.?)?\s*)?"
    r"(\d{1,3}|[a-z])\s*[.):\]]\s*(?=\S)|"          # 1.  1)  a)  Item 1:
    r"^\s*(?:item|line)\s*(\d{1,3})\s*[-–:]?\s+|"   # Item 1 -
    r"^\s*[•●▪◦*–-]\s+",                             # bullets
    re.I,
)

MAKES = [
    (re.compile(r"\bABB\b", re.I), "ABB"),
    (re.compile(r"\bSchneider(?:\s+Electric)?\b|\bSE\b(?=\s+make)", re.I), "Schneider Electric"),
    (re.compile(r"\bSiemens\b", re.I), "Siemens"),
    (re.compile(r"\bLucy(?:\s+Electric)?\b", re.I), "Lucy Electric"),
    (re.compile(r"\bLegrand\b", re.I), "Legrand"),
    (re.compile(r"\bL\s*&\s*T\b|\bLarsen\s*(?:&|and)\s*Toubro\b", re.I), "L&T"),
    (re.compile(r"\bEaton\b", re.I), "Eaton"),
    (re.compile(r"\bHager\b", re.I), "Hager"),
    (re.compile(r"\bMitsubishi(?:\s+Electric)?\b", re.I), "Mitsubishi Electric"),
    (re.compile(r"\bHavells\b", re.I), "Havells"),
    (re.compile(r"\bPhoenix\s+Contact\b", re.I), "Phoenix Contact"),
    (re.compile(r"\bRittal\b", re.I), "Rittal"),
]
MAKE_LABEL_RE = re.compile(r"\b(?:make|brand|manufacturer|mfr)\s*[:\-]\s*([A-Za-z][A-Za-z&. ]{1,29}?)(?=[,;|]|\s{2,}|$|\s+(?:part|cat|code|qty|quantity)\b)", re.I)
CODE_LABEL_RE = re.compile(
    r"\b(?:part\s*(?:no|number|code)|cat(?:alogue|alog)?\.?\s*(?:no|number|ref)?|"
    r"order(?:ing)?\s*code|model\s*no|code|ref(?:erence)?|mlfb)\b\.?\s*(?:no\.?)?\s*[:#\-]\s*"
    r"([A-Za-z0-9][\w./-]*(?:\s*\([^)]*\))?)",
    re.I,
)
# Technical values that look like codes but are not: 32A, 415V, 4P, 50kA,
# IP65, 2.5sqmm, 18-25A, 220-240VAC, 8/20, 3RV, 30mA ...
SPEC_RE = re.compile(
    r"^(?:\d+(?:[.,]\d+)?(?:[-/]\d+(?:[.,]\d+)?)*"
    r"(?:A|AMPS?|KA|MA|V|VAC|VDC|KV|KW|W|HZ|P|POLES?|MM|SQMM|SQ|MM2|M|AH|KVA|KVAR|"
    r"VA|C|K|CORE|C|S|MS|SEC|MIN|DEG|X)?|IP\d{2}|IK\d{2}|AC-?\d+[A-Z]?|DC-?\d+|"
    r"[A-Z]{1,3}\d?)$",
    re.I,
)
CODE_TOKEN_RE = re.compile(r"(?<![\w/-])[A-Za-z0-9][A-Za-z0-9./-]{3,}[A-Za-z0-9](?![\w-])")
SPEC_WORD_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:A|kA|mA|V|VAC|VDC|kW|Hz|P|pole|poles|core|sqmm|mm)\b", re.I)
PRODUCT_WORDS_RE = re.compile(
    r"\b(?:mcb|mccb|acb|rccb|rcbo|elcb|rcd|spd|breaker|contactor|relay|switch|isolator|"
    r"disconnector|fuse|cable|meter|ammeter|voltmeter|lamp|indicator|timer|panel|enclosure|"
    r"busbar|transformer|starter|drive|vfd|plc|module|terminal|socket|lug|gland|ct|"
    r"push\s*button|selector)\b",
    re.I,
)
PROSE_START_RE = re.compile(
    r"^(?:please|kindly|we|i|our|could|can|would|thank|thanks|dear|hi|hello|regards|note|"
    r"yes|ok|okay|sure|also|as|go|same|"
    r"delivery|payment|validity|terms|the|this|attached|find|looking|request|let|if)\b",
    re.I,
)

# Email noise.
QUOTE_HEADER_RE = re.compile(r"^\s*(?:On\s.+wrote:|-{2,}\s*Original Message\s*-{2,}|From:\s.+|Sent:\s.+)\s*$", re.I)
SIGN_OFF_RE = re.compile(
    r"^\s*(?:best|kind|warm|many)?\s*(?:regards|thanks|thank you|thanks\s*(?:&|and)\s*regards|"
    r"sincerely|cheers|yours\s+(?:faithfully|sincerely|truly))\b[\s,.!]*$|^\s*--\s*$",
    re.I,
)

NO_CODE_NOTE_RE = re.compile(
    r"\(\s*((?:[^()]*\b(?:to be confirmed|tbc|tba|by supplier|code not (?:known|available)|"
    r"please (?:advise|suggest|offer))\b[^()]*))\)",
    re.I,
)
LABEL_LINE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ./#]{1,30}?)\s*[:=]\s*(.+?)\s*$")
TABLE_SPLIT_RE = re.compile(r"\t+|\s*\|\s*|\s{2,}")


# ------------------------------------------------------------ email clean-up
def strip_email_noise(lines):
    """(main part, quoted part) - the reply chain and signature are split off.
    The quoted part is still used if the main part has no items (a customer
    replying 'see the list below')."""
    main, quoted, in_quote = [], [], False
    for line in lines:
        if not in_quote and QUOTE_HEADER_RE.match(line):
            in_quote = True
        if in_quote or line.lstrip().startswith(">"):
            quoted.append(re.sub(r"^\s*(?:>\s?)+", "", line))
            continue
        main.append(line)

    # Drop the signature: everything after the last sign-off line.
    for i in range(len(main) - 1, -1, -1):
        if SIGN_OFF_RE.match(main[i]):
            main = main[:i]
            break
    return main, quoted


# ------------------------------------------------------------ pasted tables
def _pasted_table(lines, source):
    rows = [[clean(c) for c in TABLE_SPLIT_RE.split(line.strip())] for line in lines]
    for i, row in enumerate(rows):
        if len(row) >= 3 and map_header(row):
            body = [r for r in rows[i:] if len(r) >= 2]
            found = lines_from_tables([(f"{source}, pasted table", body)])
            if not found.empty:
                return found
    return None


# ------------------------------------------------------------ one line
def _find_qty(text):
    """Return (qty, unit, text_without_qty) or (None, '', text)."""
    for pattern in (QTY_LABEL_RE, QTY_TIMES_START_RE, QTY_TIMES_END_RE):
        match = pattern.search(text)
        if match:
            unit = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            rest = text[: match.start()] + " " + text[match.end():]
            return to_number(match.group(1)), clean(unit or ""), rest
    matches = list(QTY_UNIT_RE.finditer(text))
    if matches:
        match = matches[-1]                     # the quantity is usually last
        rest = text[: match.start()] + " " + text[match.end():]
        return to_number(match.group(1)), clean(match.group(2)), rest
    return None, "", text


def _find_make(text):
    label = MAKE_LABEL_RE.search(text)
    if label:
        rest = text[: label.start()] + " " + text[label.end():]
        return normalise_make(label.group(1)), rest
    for pattern, name in MAKES:
        match = pattern.search(text)
        if match:
            return name, text[: match.start()] + " " + text[match.end():]
    return "", text


def _looks_like_code(token, allow_all_digits):
    bare = token.strip(".,;:/-")
    if len(bare) < 5 or SPEC_RE.match(bare):
        return False
    digits = sum(ch.isdigit() for ch in bare)
    letters = sum(ch.isalpha() for ch in bare)
    if letters == 0:
        return allow_all_digits and digits >= 5
    if digits < 2:
        return False
    # Dates and ranges like 15/10/2026 or 100-630 are not codes.
    if re.fullmatch(r"[\d/.-]+", bare):
        return False
    return True


def _find_code(text, has_make):
    label = CODE_LABEL_RE.search(text)
    if label:
        rest = text[: label.start()] + " " + text[label.end():]
        return label.group(1), rest
    tokens = [m for m in CODE_TOKEN_RE.finditer(text) if _looks_like_code(m.group(0), has_make)]
    if not tokens:
        return "", text

    def score(match):
        token = match.group(0)
        return (sum(c.isdigit() for c in token), len(token))

    best = max(tokens, key=score)
    code = best.group(0)
    end = best.end()
    note = re.match(r"\s*(\([^)]*\))", text[end:])  # '1SBL... (coil 230V)'
    if note:
        code += " " + note.group(1)
        end += note.end()
    return code, text[: best.start()] + " " + text[end:]


LEAD_IN_RE = re.compile(
    r"^\s*(?:(?:please|kindly)\s+)?(?:(?:quote|supply|send|offer|provide)(?:\s+(?:us|for|your best price for))*|"
    r"(?:we\s+)?(?:need|require|want|are looking for)|(?:our\s+)?requirement\s*(?:is|:)?)\s*[:\-]?\s*",
    re.I,
)


def _tidy_description(text):
    text = LEAD_IN_RE.sub("", clean(text))
    text = re.sub(r"\b(?:description|desc|item|details|particulars)\b\s*[:\-]\s*", "", text, flags=re.I)
    text = re.sub(r"\b(?:make|brand)\b\.?", " ", text, flags=re.I)   # 'ABB make'
    text = re.sub(r"\(\s*\)", " ", text)
    text = re.sub(r"\s*([,;|])\s*(?:[,;|]\s*)+", r"\1 ", text)        # ', ,' -> ','
    text = re.sub(r"\s+[-–:]\s+(?=[-–:]|$)", " ", text)
    text = clean(text)
    return text.strip(" ,;:|-–.")


def parse_item_line(text):
    """Pull item fields out of one line. Returns a dict, or None if the line
    is not an item."""
    original = clean(text)
    if not original:
        return None

    line_no = ""
    prefix = LIST_PREFIX_RE.match(original)
    body = original
    if prefix:
        number = prefix.group(1) or prefix.group(2) or ""
        line_no = number
        body = original[prefix.end():]

    qty, unit, rest = _find_qty(body)
    make, rest = _find_make(rest)
    code, rest = _find_code(rest, has_make=bool(make))

    # '(part code to be confirmed)', '(TBC)' written in the text: a code note.
    notes = []
    for match in list(NO_CODE_NOTE_RE.finditer(rest)):
        notes.append(clean(match.group(1)))
    rest = NO_CODE_NOTE_RE.sub(" ", rest)
    description = _tidy_description(rest)

    product_cue = bool(code or make or SPEC_WORD_RE.search(body) or PRODUCT_WORDS_RE.search(body))
    if qty is None and not (prefix and product_cue):
        return None
    if PROSE_START_RE.match(body) and not (code or make):
        return None
    if not (description or code):
        return None
    # A quantity alone is not enough ('...go ahead, but qty 30'): without a
    # list number the line also needs product details.
    if qty is not None and not product_cue and (len(description.split()) < 2 or not prefix):
        return None

    part_code, note = split_code_note(code)
    note = "; ".join(n for n in [note] + notes if n)
    return {
        "line_no": line_no,
        "description": description,
        "make": make,
        "part_code": part_code,
        "code_note": note,
        "qty": qty,
        "unit": unit,
    }


def _items_on_line(line):
    """Usually one item a line; 'MCB 32A, 24 pcs; MCCB 100A, 4 pcs' is two."""
    parts = [p for p in re.split(r"\s*;\s*", line) if clean(p)]
    if len(parts) > 1:
        items = [parse_item_line(p) for p in parts]
        if sum(1 for i in items if i and i["qty"] is not None) >= 2:
            return [i for i in items if i]
    item = parse_item_line(line)
    return [item] if item else []


# ------------------------------------------------------------ labelled blocks
FIELD_FOR_LABEL = {}
for _field, _names in SYNONYMS.items():
    for _name in _names:
        FIELD_FOR_LABEL[_name] = _field
FIELD_FOR_LABEL.update({"desc": "description", "itemno": "line_no", "lineno": "line_no",
                        "catalogueno": "part_code", "catno": "part_code", "partnos": "part_code",
                        "partnumber": "part_code", "brand": "make", "quantity": "qty"})
# In emails these labels usually mean the enquiry, not an item.
for _name in ("reference", "supplier", "item", "no", "pos", "position", "serial"):
    FIELD_FOR_LABEL.pop(_name, None)


def _label_field(line):
    match = LABEL_LINE_RE.match(line)
    if not match:
        return None, None
    return FIELD_FOR_LABEL.get(header_key(match.group(1))), match.group(2)


def _finish_block(block):
    qty_text = block.get("qty", "")
    qty, unit, _ = _find_qty("qty " + qty_text) if qty_text else (None, "", "")
    code, note = split_code_note(block.get("part_code", ""))
    return {
        "line_no": clean(block.get("line_no", "")),
        "description": clean(block.get("description", "")),
        "make": normalise_make(block.get("make", "")),
        "part_code": code,
        "code_note": note,
        "qty": qty,
        "unit": clean(block.get("unit", "")) or unit,
    }


# ------------------------------------------------------------ main entry
def _parse(lines, source):
    pasted = _pasted_table(lines, source)
    if pasted is not None:
        return pasted

    found = []
    block, block_line = {}, None

    def flush():
        nonlocal block, block_line
        if block.get("description") or block.get("part_code"):
            item = _finish_block(block)
            item["source"] = f"{source}, line {block_line}"
            found.append(item)
        block, block_line = {}, None

    for number, line in enumerate(lines, start=1):
        if not clean(line):
            continue
        field, value = _label_field(line)
        if field:
            if field in block:                 # same label again: next item
                flush()
            if block_line is None:
                block_line = number
            block[field] = value
            continue

        # 'Item 1' or '1.' on its own starts a new labelled block.
        alone = LIST_PREFIX_RE.match(clean(line))
        if alone and not clean(line)[alone.end():]:
            flush()
            block = {"line_no": alone.group(1) or alone.group(2) or ""}
            block_line = number
            continue

        # A bare '10 nos' under a labelled block is that block's quantity.
        qty, _, rest = _find_qty(clean(line))
        if block and qty is not None and not _tidy_description(rest):
            block["qty"] = clean(line)
            continue

        for item in _items_on_line(line):
            flush()
            item["source"] = f"{source}, line {number}"
            found.append(item)
    flush()

    # Number the lines that had no number of their own.
    for i, item in enumerate(found, start=1):
        if not item["line_no"]:
            item["line_no"] = str(i)
    return pd.DataFrame(found, columns=OUTPUT_COLUMNS)


def lines_from_text(text_lines, source="text") -> pd.DataFrame:
    """Return RFQ line items found in plain text lines (may be empty)."""
    if isinstance(text_lines, str):
        text_lines = text_lines.splitlines()
    text_lines = [str(line).replace(" ", " ") for line in text_lines]
    main, quoted = strip_email_noise(text_lines)
    found = _parse(main, source)
    if found.empty and quoted:
        found = _parse(quoted, f"{source} (quoted)")
    return found

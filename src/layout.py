"""Rebuild table rows from positioned text.

Used for two kinds of page where pdfplumber finds no table:
  * scanned pages, where the text comes from OCR (src/ocr.py), and
  * PDF pages whose table has no ruled lines (words from pdfplumber).

Input is a list of "boxes": dicts with text, x0, y0, x1, y1 (pixels or points,
y grows downwards) and score (OCR confidence, 1.0 for real PDF text).

How it works
------------
1. Group boxes into visual rows by their vertical centre.
2. Find the header row with the same column names as normal tables
   (extract_rfq.map_header).
3. Every number sitting under the "No." column (or "Qty" if there is no
   number column) starts one RFQ line - an "anchor".
4. Columns are the vertical strips of white space between boxes; each strip
   is given the header name above it.
5. Every box below the header goes to the nearest anchor (vertically) and to
   its column, so descriptions that wrap over 2-3 lines stay together.
The result is plain rows (header first) that extract_rfq.lines_from_tables
already understands.
"""

import re
import statistics

from src.extract_rfq import clean, map_header

NUMBER_RE = re.compile(r"^\d{1,4}(?:\.\d+)?\.?$")
LOW_CONFIDENCE = 0.8


def _mid_y(box):
    return (box["y0"] + box["y1"]) / 2


def _mid_x(box):
    return (box["x0"] + box["x1"]) / 2


def _line_height(boxes):
    heights = [b["y1"] - b["y0"] for b in boxes if b["y1"] > b["y0"]]
    return statistics.median(heights) if heights else 10.0


def group_rows(boxes):
    """Boxes -> list of rows (each a list of boxes, left to right)."""
    if not boxes:
        return []
    height = _line_height(boxes)
    rows = []
    for box in sorted(boxes, key=_mid_y):
        if rows and abs(_mid_y(box) - rows[-1]["y"]) <= 0.5 * height:
            rows[-1]["boxes"].append(box)
            count = len(rows[-1]["boxes"])
            rows[-1]["y"] += (_mid_y(box) - rows[-1]["y"]) / count
        else:
            rows.append({"y": _mid_y(box), "boxes": [box]})
    return [sorted(r["boxes"], key=lambda b: b["x0"]) for r in rows]


def merge_words(words, gap_factor=0.6):
    """PDF words -> phrases: words on one line with a small gap are joined,
    so 'Part' 'Code' becomes one header cell 'Part Code'."""
    phrases = []
    for row in group_rows(words):
        current = None
        for word in row:
            gap_limit = gap_factor * (word["y1"] - word["y0"])
            if current and word["x0"] - current["x1"] <= gap_limit:
                current["text"] += " " + word["text"]
                current["x1"] = max(current["x1"], word["x1"])
                current["y0"] = min(current["y0"], word["y0"])
                current["y1"] = max(current["y1"], word["y1"])
                current["score"] = min(current["score"], word["score"])
            else:
                current = dict(word)
                phrases.append(current)
    return phrases


def text_lines(boxes):
    """Plain text lines (cells separated by two spaces), top to bottom."""
    return ["  ".join(clean(b["text"]) for b in row) for row in group_rows(boxes)]


def cell_rows(boxes):
    """Every visual row as a list of cell texts - lets the header reader find
    'RFQ No. | KBS/...' style label/value pairs on scanned pages."""
    return [[clean(b["text"]) for b in row] for row in group_rows(boxes)]


def _columns(body, header_cells, shrink):
    """Split the body into column strips at vertical white space."""
    spans = sorted(
        (b["x0"] + shrink, b["x1"] - shrink)
        for b in body
        if b["x1"] - b["x0"] > 2 * shrink
    )
    strips = []
    for x0, x1 in spans:
        if strips and x0 <= strips[-1][1]:
            strips[-1][1] = max(strips[-1][1], x1)
        else:
            strips.append([x0, x1])

    # Give each strip the header cell that overlaps it most (else nearest).
    named = []
    for x0, x1 in strips:
        def overlap(cell):
            return min(x1, cell["x1"]) - max(x0, cell["x0"])
        best = max(header_cells, key=overlap)
        if overlap(best) <= 0:
            centre = (x0 + x1) / 2
            best = min(header_cells, key=lambda c: abs(_mid_x(c) - centre))
        named.append((x0 - shrink, x1 + shrink, header_cells.index(best)))
    return named


def _column_of(box, columns, header_cells):
    centre = _mid_x(box)
    for x0, x1, index in columns:
        if x0 <= centre <= x1:
            return index
    return min(range(len(header_cells)), key=lambda i: abs(_mid_x(header_cells[i]) - centre))


def _column_span(index, columns, header_cells):
    """Left and right edge of a column: its white-space strip(s), widened to
    the header cell above it."""
    cell = header_cells[index]
    x0, x1 = cell["x0"], cell["x1"]
    for left, right, owner in columns:
        if owner == index:
            x0, x1 = min(x0, left), max(x1, right)
    return x0, x1


def _add_missed_line_numbers(anchors, below, header_cells, header_mapping, anchor_cell, height, reread):
    """OCR sometimes misses a lone '1' in the No. column. A quantity (or a
    unit such as 'Nos') with no line number beside it still starts an item:
    look at the No. cell again, or work the number out from the lines around
    it."""
    def under(field, numeric):
        index = next((i for i, f in header_mapping.items() if f == field), None)
        if index is None or index >= len(header_cells):
            return []
        cell = header_cells[index]
        half = (cell["x1"] - cell["x0"]) / 2
        return [
            b for b in below
            if (not numeric or NUMBER_RE.match(clean(b["text"])))
            and clean(b["text"])
            and cell["x0"] - half <= _mid_x(b) <= cell["x1"] + half
        ]

    quantities = sorted(under("qty", True) + under("unit", False), key=_mid_y)
    if not anchors or not quantities:
        return anchors
    last = max(_mid_y(a) for a in anchors) + 2 * height

    added = []
    for qty in quantities:
        if _mid_y(qty) > last:
            continue
        if any(abs(_mid_y(a) - _mid_y(qty)) < 0.6 * height for a in anchors + added):
            continue
        text, score = "", 0.0
        if reread:
            text, score = reread(anchor_cell["x0"] - (anchor_cell["x1"] - anchor_cell["x0"]),
                                 qty["y0"] - 0.4 * height,
                                 anchor_cell["x1"] + (anchor_cell["x1"] - anchor_cell["x0"]),
                                 qty["y1"] + 0.4 * height)
            text = clean(text) if NUMBER_RE.match(clean(text)) else ""
        added.append({"text": text, "x0": anchor_cell["x0"], "x1": anchor_cell["x1"],
                      "y0": qty["y0"], "y1": qty["y1"], "score": min(score, 0.0)})
    if not added:
        return anchors

    merged = sorted(anchors + added, key=_mid_y)
    # Fill numbers we could not read from the neighbours: 1, ?, 3 -> 2.
    for i, anchor in enumerate(merged):
        if anchor["text"]:
            continue
        before = _as_int(merged[i - 1]["text"]) if i > 0 else 0
        after = _as_int(merged[i + 1]["text"]) if i + 1 < len(merged) else None
        if before is not None and (after is None or after == before + 2):
            anchor["text"] = str(before + 1)
        elif after is not None and after > 1:
            anchor["text"] = str(after - 1)
    return merged


def _as_int(text):
    text = clean(text).rstrip(".")
    return int(text) if text.isdigit() else None


def find_header(rows):
    """Return (row_index, mapping) of the first header-looking row."""
    for i, row in enumerate(rows):
        mapping = map_header([b["text"] for b in row])
        if mapping:
            return i, mapping
    return None, None


def table_from_boxes(boxes, header_cells=None, header_mapping=None, reread=None):
    """Return (rows, header_cells, header_mapping, low_confidence_line_nos).

    rows is [] when no table was found. header_cells/mapping can be passed in
    from the previous page for tables that continue without a header.
    reread(x0, y0, x1, y1) -> (text, score) is optional: it is called for an
    empty quantity cell, so OCR can look at that spot again more closely.
    """
    rows = group_rows(boxes)
    if not rows:
        return [], header_cells, header_mapping, []

    index, mapping = find_header(rows)
    if mapping is not None:
        header_cells, header_mapping = rows[index], mapping
        top = max(b["y1"] for b in header_cells)
    elif header_cells is not None:
        top = min(b["y0"] for b in boxes) - 1      # continuation page
    else:
        return [], None, None, []

    height = _line_height(boxes)
    below = [b for b in boxes if _mid_y(b) > top and b not in header_cells]

    # Anchors: numbers under the line-number column (or the qty column).
    anchor_field = "line_no" if "line_no" in header_mapping.values() else "qty"
    anchor_cell = header_cells[
        next(i for i, f in header_mapping.items() if f == anchor_field)
    ]
    width = anchor_cell["x1"] - anchor_cell["x0"]
    lo, hi = anchor_cell["x0"] - width, anchor_cell["x1"] + width
    anchors = sorted(
        (b for b in below if NUMBER_RE.match(clean(b["text"])) and lo <= _mid_x(b) <= hi),
        key=_mid_y,
    )
    if anchor_field == "line_no":
        anchors = _add_missed_line_numbers(anchors, below, header_cells, header_mapping,
                                           anchor_cell, height, reread)
    if not anchors:
        return [], header_cells, header_mapping, []

    # The table ends at the first big vertical gap between line numbers
    # (e.g. a page number or a "Notes" paragraph further down).
    kept = [anchors[0]]
    for anchor in anchors[1:]:
        if _mid_y(anchor) - _mid_y(kept[-1]) > 8 * height:
            break
        kept.append(anchor)
    anchors = kept
    bottom = _mid_y(anchors[-1]) + 2 * height
    body = [b for b in below if _mid_y(b) <= bottom]

    columns = _columns(body, header_cells, shrink=0.3 * height)
    cells = [[[] for _ in header_cells] for _ in anchors]
    low = set()
    for box in body:
        if box in anchors:
            continue
        item = min(range(len(anchors)), key=lambda i: abs(_mid_y(anchors[i]) - _mid_y(box)))
        cells[item][_column_of(box, columns, header_cells)].append(box)
        if box["score"] < LOW_CONFIDENCE:
            low.add(item)

    anchor_col = header_cells.index(anchor_cell)
    qty_col = next((i for i, f in header_mapping.items() if f == "qty"), None)
    if qty_col is not None and qty_col >= len(header_cells):
        qty_col = None
    result = [[clean(c["text"]) for c in header_cells]]
    for item, anchor in enumerate(anchors):
        cells[item][anchor_col].insert(0, anchor)
        if anchor["score"] < LOW_CONFIDENCE:
            low.add(item)
        row = []
        for column in cells[item]:
            column.sort(key=lambda b: (round(_mid_y(b) / height), b["x0"]))
            row.append(" ".join(clean(b["text"]) for b in column))
        row[anchor_col] = clean(anchor["text"]).rstrip(".")

        if reread and qty_col is not None and qty_col != anchor_col and not row[qty_col]:
            x0, x1 = _column_span(qty_col, columns, header_cells)
            text, score = reread(x0, anchor["y0"] - 0.4 * height, x1, anchor["y1"] + 0.4 * height)
            if NUMBER_RE.match(clean(text)):
                row[qty_col] = clean(text).rstrip(".")
                low.add(item)          # read on a second try: worth a look
        result.append(row)
    flagged = [clean(anchors[i]["text"]).rstrip(".") for i in sorted(low)]
    return result, header_cells, header_mapping, flagged


def tidy_ocr_text(text):
    """Put back spaces the OCR model tends to drop in descriptions:
    after commas ('Breaker,3pole' -> 'Breaker, 3pole') and between glued
    capitalised words ('MiniatureCircuitBreaker' -> 'Miniature Circuit Breaker').
    """
    text = re.sub(r",(?=[A-Za-z]|\d(?!\d{2}\b))", ", ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z][a-z]+(?:[A-Z][a-z]+)*\b)", " ", text)
    return re.sub(r"\s+", " ", text).strip()

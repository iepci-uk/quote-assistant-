"""Read scanned RFQs (PDF pages with no text, or photos) with Tesseract OCR.

    from src.ocr_rfq import ocr_pdf_pages, ocr_image
    pages = ocr_pdf_pages("scan.pdf")       # {page number: OcrPage}

or, to see what OCR made of a file:
    python -m src.ocr_rfq scan.pdf
    python -m src.ocr_rfq scan.pdf --compare data/raw/RFQ_KBS-0147.pdf

How it works
------------
1. Each page becomes a 300 dpi greyscale image. It is turned upright
   (Tesseract's orientation check) and straightened (the small angle that
   makes the text rows sharpest).
2. Ruled tables: the table lines are found with long thin image filters and
   give a grid of cells. Every cell is read on its own, so text from one
   column can never run into the next. Cells read with low confidence are
   read again from an enlarged, black-and-white copy and the better reading
   is kept. Quantity and number columns are re-read as digits only.
3. Tables without lines: the words are grouped into rows, and the header
   row ("Description", "Qty", ...) gives the column positions for the rows
   below it.
4. The rows go to the same table reader as text PDFs (extract_rfq), so the
   header synonyms and part-code rules are identical. Rows with any cell read
   below LOW_CONFIDENCE get "(OCR, check)" in their source.
"""

import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

DPI = 300
LOW_CONFIDENCE = 80                 # Tesseract word confidence, 0-100
DEFAULT_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
WORKERS = min(8, os.cpu_count() or 2)


@dataclass
class OcrPage:
    tables: list = field(default_factory=list)       # (location, rows, row_sources)
    text_lines: list = field(default_factory=list)


# ------------------------------------------------------------ tesseract
def find_tesseract():
    """Return pytesseract, pointed at the Tesseract program."""
    import pytesseract

    for candidate in (os.environ.get("TESSERACT_CMD"), shutil.which("tesseract"), DEFAULT_TESSERACT):
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return pytesseract
    raise RuntimeError(
        "Tesseract OCR is needed to read scanned RFQs but was not found. Install it "
        "(https://github.com/UB-Mannheim/tesseract/wiki) or set TESSERACT_CMD to tesseract.exe."
    )


def read_words(image, config="--psm 6"):
    """OCR an image. Returns a list of words: text, confidence and box."""
    tess = find_tesseract()
    data = tess.image_to_data(image, config=config, output_type=tess.Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        words.append({
            "text": text,
            "conf": conf,
            "left": data["left"][i],
            "top": data["top"][i],
            "right": data["left"][i] + data["width"][i],
            "bottom": data["top"][i] + data["height"][i],
            "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
        })
    return words


def words_to_text(words):
    """Words in reading order -> text, one output line per OCR line."""
    lines = {}
    for word in words:
        lines.setdefault(word["line"], []).append(word["text"])
    return tidy_units("\n".join(" ".join(parts) for parts in lines.values()))


def tidy_units(text):
    """OCR often capitalises the k / m of units: '36 KA' -> '36 kA', '30 MA' -> '30 mA'."""
    text = re.sub(r"(\d)(\s?)K(VA|VAr|A|V|W)\b", r"\1\2k\3", text)
    return re.sub(r"(\d)(\s?)MA\b", r"\1\2mA", text)


def mean_conf(words):
    return sum(w["conf"] for w in words) / len(words) if words else 100.0


# ------------------------------------------------------------ image prep
def to_gray(image):
    import cv2

    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    # Photos and low-resolution scans: enlarge so text is ~300 dpi size.
    if gray.shape[1] < 2000:
        scale = 2480 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return gray


def ink_mask(gray):
    """255 where the page is dark (text, lines), 0 elsewhere."""
    import cv2

    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 15
    )


def solid_text(gray):
    """Black text on white, for reading whole pages.

    Each pixel is compared with the paper around it, so coloured letterheads
    (orange, light blue) come out solid black, and thick bold letters are not
    hollowed out as they are by ink_mask.
    """
    import cv2

    paper = cv2.dilate(gray, np.ones((31, 31), np.uint8))
    level = cv2.divide(gray, paper, scale=255)
    return np.where(level < 215, 0, 255).astype(np.uint8)


def rotate(image, angle, fill):
    import cv2

    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC, borderValue=fill)


def fix_orientation(gray):
    """Turn pages scanned sideways or upside down the right way up."""
    import cv2

    tess = find_tesseract()
    try:
        osd = tess.image_to_osd(gray, config="--psm 0 -c min_characters_to_try=10")
    except tess.TesseractError:
        return gray
    angle = int(re.search(r"Rotate: (\d+)", osd).group(1))
    confidence = float(re.search(r"Orientation confidence: ([\d.]+)", osd).group(1))
    turns = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    if angle in turns and confidence >= 1.5:
        return cv2.rotate(gray, turns[angle])
    return gray


def skew_angle(gray):
    """Small rotation (degrees) that makes the text rows sharpest."""
    import cv2

    ink = ink_mask(gray)
    scale = 1000 / ink.shape[1]
    small = cv2.resize(ink, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    def sharpness(angle):
        rows = rotate(small, angle, 0).sum(axis=1).astype(float)
        return float(np.sum(np.diff(rows) ** 2))

    best = max(np.arange(-10, 10.01, 0.5), key=sharpness)
    return max(np.arange(best - 0.5, best + 0.51, 0.05), key=sharpness)


def prepare(image):
    """PIL page image -> upright, straight, denoised greyscale numpy image."""
    import cv2

    gray = cv2.fastNlMeansDenoising(to_gray(image), None, h=12, templateWindowSize=7, searchWindowSize=21)
    gray = fix_orientation(gray)
    angle = skew_angle(gray)
    if abs(angle) >= 0.05:
        gray = rotate(gray, angle, 255)
    return gray


# ------------------------------------------------------------ ruled tables
def ruling_lines(ink):
    """Masks of the long horizontal and vertical lines on the page."""
    import cv2

    h, w = ink.shape
    across = cv2.getStructuringElement(cv2.MORPH_RECT, (max(w // 30, 40), 1))
    down = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(h // 60, 45)))
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, across)
    vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, down)
    # Join small breaks in scanned lines.
    horizontal = cv2.morphologyEx(horizontal, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1)))
    vertical = cv2.morphologyEx(vertical, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25)))
    return horizontal, vertical


def line_positions(coverage, minimum):
    """Centres of runs where coverage >= minimum (one per drawn line)."""
    positions, start = [], None
    for i, value in enumerate(list(coverage) + [0]):
        if value >= minimum and start is None:
            start = i
        elif value < minimum and start is not None:
            positions.append((start + i - 1) // 2)
            start = None
    return positions


def find_grids(horizontal, vertical):
    """Ruled tables on the page: a list of grids, each a list of rows of cell boxes."""
    import cv2

    page_h, page_w = horizontal.shape
    joined = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((5, 5), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined)

    grids = []
    for x, y, w, h, _ in stats[1:count]:
        if w < page_w * 0.2 or h < 40:
            continue
        across = (horizontal[y:y + h, x:x + w] > 0).sum(axis=1)
        ys = line_positions(across, w * 0.5)
        rows = []
        for top, bottom in zip(ys, ys[1:]):
            top, bottom = y + top, y + bottom
            if bottom - top < 20:
                continue
            band = vertical[top + 5:bottom - 5, x:x + w] > 0
            xs = line_positions(band.sum(axis=0), band.shape[0] * 0.6)
            if len(xs) < 2:
                continue
            rows.append([(x + left, top, x + right, bottom) for left, right in zip(xs, xs[1:]) if right - left > 10])
        if len(rows) >= 2:
            grids.append(rows)
    return sorted(grids, key=lambda grid: grid[0][0][1])


def crop(gray, box, inset=6):
    left, top, right, bottom = box
    return gray[top + inset:bottom - inset, left + inset:right - inset]


def pad(image, border=20):
    import cv2

    return cv2.copyMakeBorder(image, border, border, border, border, cv2.BORDER_CONSTANT, value=255)


def enlarged_bw(image):
    import cv2

    big = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def text_marks(image):
    """Boxes (x, y, w, h, area) of the marks in a cell big enough to be text."""
    import cv2

    if image.size == 0:
        return []
    ink = cv2.morphologyEx(ink_mask(image), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink)
    return [s for s in stats[1:count] if s[3] >= 12 and s[4] >= 30]


def has_text(image):
    """False for empty cells, including ones with only scanner specks."""
    return bool(text_marks(image))


def read_cell(image):
    """Best reading of one table cell: (text, confidence)."""
    if not has_text(image):
        return "", 100.0
    best = ("", -1.0)
    for picture in (image, enlarged_bw(image)):
        words = read_words(pad(picture), "--psm 6")
        reading = (words_to_text(words), mean_conf(words))
        if reading[1] > best[1]:
            best = reading
        if best[1] >= LOW_CONFIDENCE:
            break
    return best


DIGITS = "-c tessedit_char_whitelist=0123456789."
NUMBER_HEIGHTS = (16, 20, 24)       # pixel heights digits are read at (tested best)


def ink_box(image):
    """The part of a cell that holds text (specks ignored)."""
    marks = text_marks(image)
    left = min(s[0] for s in marks)
    top = min(s[1] for s in marks)
    right = max(s[0] + s[2] for s in marks)
    bottom = max(s[1] + s[3] for s in marks)
    return image[top:bottom, left:right]


def read_number(image):
    """Read a quantity / line number by vote; (text, confidence).

    Tesseract is weakest on a lone digit in an empty cell (1 read as 4, a 9
    read as nothing). The digits are cut out and read at three sizes; the
    answer only counts as sure when all three agree. Otherwise the most
    common reading is returned with confidence 0, so the row is checked.
    """
    import cv2
    from collections import Counter

    if not has_text(image):
        return "", 100.0
    digits = ink_box(image)
    readings = []
    for height in NUMBER_HEIGHTS:
        scale = height / digits.shape[0]
        sized = cv2.resize(digits, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        words = read_words(pad(sized, 15), f"--psm 7 {DIGITS}")
        text = "".join(w["text"] for w in words).strip(".")
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            readings.append((text, mean_conf(words)))
    if not readings:
        return read_cell(image)[0], 0.0
    text, count = Counter(t for t, _ in readings).most_common(1)[0]
    if count < len(NUMBER_HEIGHTS):
        return text, 0.0
    return text, max(c for t, c in readings if t == text)


def fix_header_cells(row):
    """Header words misread by one letter ('aty' for 'Qty') -> the known word."""
    from src.code_correction import one_edit_apart
    from src.extract_rfq import SYNONYMS, header_key

    known = {name for names in SYNONYMS.values() for name in names}
    fixed = []
    for cell in row:
        key = header_key(cell)
        if key and key not in known and len(key) >= 3:
            close = [name for name in known if len(name) >= 3 and one_edit_apart(key, name)]
            if len(close) == 1:
                cell = close[0]
        fixed.append(cell)
    return fixed


def find_header(rows):
    """(row index, {column: field}) of the table header, or (None, {})."""
    from src.extract_rfq import map_header

    for r, row in enumerate(rows[:30]):
        mapping = map_header(row) or map_header(fix_header_cells(row))
        if mapping:
            return r, mapping
    return None, {}


def read_grid(gray, grid, previous=None):
    """OCR every cell of a ruled table.

    previous: (column count, fields) of the table before, for tables that
    continue on the next page without repeating the header.
    Returns (rows of text, per-row "needs checking" flags, (columns, fields)).
    """
    cleaned = lines_removed(gray)
    boxes = [box for row in grid for box in row]
    with ThreadPoolExecutor(WORKERS) as pool:
        readings = list(pool.map(lambda box: read_cell(crop(cleaned, box)), boxes))
    rows, i = [], 0
    for row in grid:
        rows.append(readings[i:i + len(row)])
        i += len(row)

    header_at, fields = find_header([[text for text, _ in row] for row in rows])
    if header_at is not None:
        rows[header_at] = [(name, 100.0) for name in fix_header_cells([t for t, _ in rows[header_at]])]
        width, start = len(rows[header_at]), header_at + 1
    elif previous and len(rows[0]) == previous[0]:
        width, fields = previous
        start = 0
    else:
        return [[t for t, _ in row] for row in rows], [False] * len(rows), previous

    # Quantity and line-number cells: read again as numbers, with a vote.
    number_columns = [c for c, name in fields.items() if name in ("qty", "line_no")]
    jobs = [(r, c) for r in range(start, len(rows)) for c in number_columns if len(rows[r]) == width]
    with ThreadPoolExecutor(WORKERS) as pool:
        numbers = list(pool.map(lambda job: read_number(crop(cleaned, grid[job[0]][job[1]])), jobs))
    for (r, c), reading in zip(jobs, numbers):
        rows[r][c] = reading

    # A row needs checking if a field we use was read with low confidence.
    # Descriptions are long and are read by a person anyway, so a lower bar.
    flags = []
    for row in rows:
        low = False
        for c, (text, conf) in enumerate(row):
            name = fields.get(c)
            if text and name and conf < (LOW_CONFIDENCE if name != "description" else 60):
                low = True
        flags.append(low)
    return [[t for t, _ in row] for row in rows], flags, (width, fields)


def lines_removed(gray):
    """Copy of the page with the table lines painted white."""
    import cv2

    horizontal, vertical = ruling_lines(ink_mask(gray))
    lines = cv2.dilate(cv2.bitwise_or(horizontal, vertical), np.ones((5, 5), np.uint8))
    cleaned = gray.copy()
    cleaned[lines > 0] = 255
    return cleaned


# ------------------------------------------------------------ unruled tables
def text_rows(words):
    """Words -> lines of text by height on the page, each sorted left to right."""
    height = np.median([w["bottom"] - w["top"] for w in words])
    lines = []
    for word in sorted(words, key=lambda w: (w["top"] + w["bottom"]) / 2):
        centre = (word["top"] + word["bottom"]) / 2
        if lines and abs(centre - lines[-1]["centre"]) < 0.5 * height:
            line = lines[-1]
            line["words"].append(word)
            line["centre"] = np.mean([(w["top"] + w["bottom"]) / 2 for w in line["words"]])
        else:
            lines.append({"words": [word], "centre": centre})
    for line in lines:
        line["words"].sort(key=lambda w: w["left"])
        line["top"] = min(w["top"] for w in line["words"])
        line["bottom"] = max(w["bottom"] for w in line["words"])
    return lines, height


def split_into_cells(words, height):
    """One line of words -> cells, split where the gap between words is wide."""
    cells = [[words[0]]]
    for previous, word in zip(words, words[1:]):
        if word["left"] - previous["right"] > 1.5 * height:
            cells.append([word])
        else:
            cells[-1].append(word)
    return cells


def column_edges(lines, height):
    """x positions between columns: gaps that stay empty down the whole table."""
    left = min(w["left"] for line in lines for w in line["words"])
    right = max(w["right"] for line in lines for w in line["words"])
    used = np.zeros(right - left + 1, dtype=int)
    for line in lines:
        for word in line["words"]:
            used[word["left"] - left:word["right"] - left + 1] += 1
    edges, start = [], None
    for x, count in enumerate(list(used) + [1]):
        if count == 0 and start is None:
            start = x
        elif count and start is not None:
            if x - start >= height:              # wider than a space between words
                edges.append(left + (start + x) // 2)
            start = None
    return left, edges, right


def unruled_grid(words):
    """A table without lines -> (grid of cell boxes, rows of words outside it).

    The header row ('No.', 'Description', 'Qty', ...) starts the table; the
    columns are the gaps that stay empty in every line below it; rows are
    split where the gap between lines is wider than within a wrapped cell,
    and every line that has its own line number or quantity starts a row.
    """
    from src.extract_rfq import map_header

    if not words:
        return None, []
    lines, height = text_rows(words)

    header_at = None
    for i, line in enumerate(lines):
        texts = [" ".join(w["text"] for w in cell) for cell in split_into_cells(line["words"], height)]
        if map_header(texts) or map_header(fix_header_cells(texts)):
            header_at = i
            break
    if header_at is None:
        return None, lines

    # The table ends at the first big vertical gap.
    end = header_at + 1
    while end < len(lines) and lines[end]["top"] - lines[end - 1]["bottom"] < 2.5 * height:
        end += 1
    table = lines[header_at:end]
    if len(table) < 2:
        return None, lines
    left, edges, right = column_edges(table[1:], height)
    bounds = [left - 10] + edges + [right + 10]

    def column_of(word):
        return sum((word["left"] + word["right"]) / 2 > edge for edge in edges)

    header_words = [[] for _ in bounds[1:]]
    for word in table[0]["words"]:
        header_words[column_of(word)].append(word["text"])
    fields = map_header(fix_header_cells([" ".join(ws) for ws in header_words])) or {}
    anchors = {c for c, name in fields.items() if name in ("line_no", "qty")}

    # Group the lines below the header into table rows.
    rows = [[table[1]]]
    for previous, line in zip(table[1:], table[2:]):
        starts_row = any(column_of(w) in anchors for w in line["words"])
        has_anchor = any(column_of(w) in anchors for ln in rows[-1] for w in ln["words"])
        if line["top"] - previous["bottom"] > 0.6 * height or (starts_row and has_anchor):
            rows.append([line])
        else:
            rows[-1].append(line)

    bands = [(table[0]["top"], table[0]["bottom"])] + [(r[0]["top"], r[-1]["bottom"]) for r in rows]
    tops = [bands[0][0] - 10] + [(a[1] + b[0]) // 2 for a, b in zip(bands, bands[1:])]
    bottoms = tops[1:] + [bands[-1][1] + 10]
    grid = [
        [(int(bounds[c]), int(top), int(bounds[c + 1]), int(bottom)) for c in range(len(bounds) - 1)]
        for top, bottom in zip(tops, bottoms)
    ]
    return grid, lines[:header_at] + lines[end:]


# ------------------------------------------------------------ pages
def row_source(location, check):
    return f"{location} (OCR, check)" if check else f"{location} (OCR)"


def ocr_page(image, label, previous=None):
    """OCR one page image. label is used in the source column, e.g. 'page 2'.

    previous: column layout of the last table on the page before.
    Returns (OcrPage, column layout of this page's last table).
    """
    gray = prepare(image)
    horizontal, vertical = ruling_lines(ink_mask(gray))
    grids = find_grids(horizontal, vertical)

    page_words = read_words(solid_text(gray), "--psm 4")
    page = OcrPage(text_lines=words_to_text(page_words).splitlines())

    for t, grid in enumerate(grids, start=1):
        rows, flags, previous = read_grid(gray, grid, previous)
        location = f"{label}, table {t}"
        page.tables.append((location, rows, [row_source(location, flag) for flag in flags]))

    if not grids:
        grid, other_lines = unruled_grid(page_words)
        if grid:
            rows, flags, previous = read_grid(gray, grid, previous)
            page.tables.append((label, rows, [row_source(label, flag) for flag in flags]))
        # 'RFQ No.   KBS/0147' lines outside the table, for the header details.
        if other_lines:
            height = np.median([w["bottom"] - w["top"] for w in page_words])
            label_rows = [
                [" ".join(w["text"] for w in cell) for cell in split_into_cells(line["words"], height)]
                for line in other_lines
            ]
            page.tables.append((f"{label}, text", label_rows))
    return page, previous


def check_line_numbers(lines):
    """OCR'd line numbers that clash with another line are fixed or flagged.

    A number read twice ('4' for line 1 and for line 4) is corrected when its
    neighbours show clearly which number it must be and that number is not
    used; otherwise the line is marked for checking.
    """
    from src.code_correction import add_note

    lines = lines.copy()
    numbers = [int(n) if str(n).isdigit() else None for n in lines["line_no"]]
    used = {n for n in numbers if n is not None}
    clashing = {n for n in numbers if n is not None and numbers.count(n) > 1}
    for i, number in enumerate(numbers):
        if number not in clashing:
            continue
        # Only neighbours whose own number is not in doubt count as evidence.
        guesses = set()
        if i > 0 and numbers[i - 1] is not None and numbers[i - 1] not in clashing:
            guesses.add(numbers[i - 1] + 1)
        if i + 1 < len(numbers) and numbers[i + 1] is not None and numbers[i + 1] not in clashing:
            guesses.add(numbers[i + 1] - 1)
        if guesses == {number}:
            continue                      # in sequence: the other one is wrong
        fixed = guesses.pop() if len(guesses) == 1 else None
        if fixed and fixed not in used:
            lines.iat[i, lines.columns.get_loc("line_no")] = str(fixed)
            note = f"line no. read as {number}, corrected to {fixed}"
            numbers[i] = fixed
            used.add(fixed)
        else:
            note = "line no. unclear, check"
        column = lines.columns.get_loc("code_note")
        lines.iat[i, column] = add_note(lines.iat[i, column], note)
    return lines


@lru_cache(maxsize=16)
def _ocr_pdf(path: str, modified: float):
    import pdfplumber

    from src.extract_rfq import is_scanned_page

    pages, layout = {}, None
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if not is_scanned_page(page):
                continue
            image = page.to_image(resolution=DPI).original
            pages[number], layout = ocr_page(image, f"page {number}", layout)
    return pages


def ocr_pdf_pages(path) -> dict:
    """{page number: OcrPage} for every page of the PDF that has no text."""
    path = Path(path)
    return _ocr_pdf(str(path.resolve()), path.stat().st_mtime)


@lru_cache(maxsize=16)
def _ocr_image(path: str, modified: float):
    from PIL import Image, ImageSequence

    with Image.open(path) as picture:
        frames = [frame.copy() for frame in ImageSequence.Iterator(picture)]
    if len(frames) == 1:
        return [ocr_page(frames[0], "image")[0]]
    pages, layout = [], None
    for number, frame in enumerate(frames, start=1):
        page, layout = ocr_page(frame, f"page {number}", layout)
        pages.append(page)
    return pages


def ocr_image(path) -> list:
    """OcrPage for each frame of an image file (multi-page TIFFs have several)."""
    path = Path(path)
    return _ocr_image(str(path.resolve()), path.stat().st_mtime)


# ------------------------------------------------------------ check
def compare(path, reference):
    """Print how many fields OCR read the same as in a reference RFQ."""
    from src.extract_rfq import extract_rfq_lines
    from src.load_price_lists import make_key

    got = extract_rfq_lines(path).set_index("line_no")
    want = extract_rfq_lines(reference).set_index("line_no")
    print(f"Lines: {len(got)} read, {len(want)} expected")
    tidy = {"part_code": make_key}
    for column in ("part_code", "qty", "make", "unit", "description"):
        same = 0
        for line_no, expected in want[column].items():
            if line_no not in got.index:
                print(f"  line {line_no}: missing")
                continue
            value = got.at[line_no, column]
            norm = tidy.get(column, lambda v: str(v).strip())
            if norm(value) == norm(expected):
                same += 1
            else:
                print(f"  line {line_no} {column}: read {value!r}, expected {expected!r}")
        print(f"{column}: {same}/{len(want)} correct")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[2] == "--compare":
        compare(sys.argv[1], sys.argv[3])
    elif len(sys.argv) == 2:
        from src.extract_rfq import extract_rfq_lines

        import pandas as pd

        pd.set_option("display.width", 200, "display.max_colwidth", 40)
        print(extract_rfq_lines(sys.argv[1]).to_string(index=False))
    else:
        sys.exit("Usage: python -m src.ocr_rfq <scan> [--compare <reference rfq>]")

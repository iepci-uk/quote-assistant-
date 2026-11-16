"""OCR for scanned PDF pages - runs fully on this computer.

Engine: RapidOCR (pip package rapidocr_onnxruntime). Its models ship inside
the package, so there is nothing else to install, no internet and no API key.
Pages are rendered to images with pypdfium2 (installed with pdfplumber).

    from src.ocr import ocr_pdf_page
    boxes = ocr_pdf_page("scan.pdf", 0)   # list of text boxes on page 1

OCR is slow (several seconds a page), so results are cached per file and
page: reading the line items and then the header only OCRs each page once.
"""

import unicodedata
from functools import lru_cache
from pathlib import Path

DPI = 300               # good balance of accuracy and speed for A4 scans
MIN_TEXT_CHARS = 20     # fewer real text characters than this = scanned page

_engine = None


def page_needs_ocr(page) -> bool:
    """True for a pdfplumber page that is an image with (almost) no text."""
    text_chars = [c for c in page.chars if c.get("text", "").strip()]
    return len(text_chars) < MIN_TEXT_CHARS and bool(page.images)


def _get_engine():
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as error:
            raise RuntimeError(
                "This PDF is scanned and needs OCR. Install it with: "
                "pip install rapidocr_onnxruntime"
            ) from error
        # The default max_side_len (2000 px) shrinks an A4 page so much that
        # the model stops seeing the spaces between words.
        _engine = RapidOCR(max_side_len=4000)
    return _engine


@lru_cache(maxsize=8)
def _page_image(path: str, mtime: float, page_index: int):
    """The page rendered as an RGB numpy array."""
    import numpy as np
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(path)
    try:
        image = pdf[page_index].render(scale=DPI / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
    return np.array(image)


def _skew(results):
    """Median tilt in degrees of the wide text lines (0 for a straight scan)."""
    import math
    import statistics

    angles = []
    for points, _, _ in results:
        (x0, y0), (x1, y1) = points[0], points[1]
        height = math.dist(points[0], points[3])
        if math.dist(points[0], points[1]) > 4 * height > 0:
            angles.append(math.degrees(math.atan2(y1 - y0, x1 - x0)))
    return statistics.median(angles) if len(angles) >= 5 else 0.0


@lru_cache(maxsize=64)
def _ocr_cached(path: str, mtime: float, page_index: int):
    import numpy as np

    image = _page_image(path, mtime, page_index)
    results = _get_engine()(image)[0] or []

    # A page fed into the scanner at an angle: turn the box positions level
    # so rows line up again. The text itself was already read correctly.
    angle = _skew(results)
    matrix = _deskew_matrix(image, angle)

    boxes = []
    for points, text, score in results:
        points = np.array(points, dtype=float)
        if matrix is not None:
            points = np.hstack([points, np.ones((len(points), 1))]) @ matrix.T
        xs, ys = points[:, 0], points[:, 1]
        boxes.append(
            {
                # The model also knows Chinese and sometimes returns full-width
                # characters on blurry text ('（' for '('); NFKC makes them plain.
                "text": unicodedata.normalize("NFKC", str(text)),
                "x0": float(xs.min()), "y0": float(ys.min()),
                "x1": float(xs.max()), "y1": float(ys.max()),
                "score": float(score),
            }
        )
    return tuple(tuple(sorted(b.items())) for b in boxes), angle


def _deskew_matrix(image, angle):
    """2x3 matrix that levels the page (None when it is already straight)."""
    if abs(angle) < 0.2:
        return None
    import cv2

    height, width = image.shape[:2]
    return cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)


def ocr_pdf_page(path, page_index: int):
    """Text boxes on one page: dicts with text, x0, y0, x1, y1, score."""
    path = Path(path).resolve()
    frozen, _ = _ocr_cached(str(path), path.stat().st_mtime, page_index)
    return [dict(b) for b in frozen]


def reread_region(path, page_index: int, x0, y0, x1, y1) -> tuple:
    """OCR one small area again, zoomed in - for a table cell that came back
    empty (a lone thin '1' is easy to miss on a noisy scan). Coordinates are
    the (levelled) ones ocr_pdf_page returns. Returns (text, score)."""
    import cv2

    path = Path(path).resolve()
    mtime = path.stat().st_mtime
    image = _page_image(str(path), mtime, page_index)
    _, angle = _ocr_cached(str(path), mtime, page_index)
    matrix = _deskew_matrix(image, angle)
    if matrix is not None:
        height, width = image.shape[:2]
        image = cv2.warpAffine(image, matrix, (width, height), borderValue=(255, 255, 255))

    height, width = image.shape[:2]
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(width, int(x1)), min(height, int(y1))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return "", 0.0
    crop = image[y0:y1, x0:x1]
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    results = _get_engine()(crop)[0] or []
    if not results:
        return "", 0.0
    results.sort(key=lambda r: r[0][0][0])
    text = unicodedata.normalize("NFKC", " ".join(str(r[1]) for r in results))
    return text.strip(), min(float(r[2]) for r in results)

# IEPCI Quote Assistant

Reads a customer RFQ (PDF, Word, Excel, a scan or photo, or an email), finds each item in the ABB and
Schneider price lists, and produces a DRAFT Excel quotation from the IEPCI
template. All amounts are in INR. A person reviews everything: a rate only
appears in the quotation when it is ticked "Rate approved". The supplier list
price (MRP, no discount) is shown next to each line, and one button can use
those list prices as the rates wherever the price is clear.

## Setup (once)

```
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt
```

For scanned RFQs, install Tesseract OCR for Windows
(https://github.com/UB-Mannheim/tesseract/wiki) with the default options. It
is found in `C:\Program Files\Tesseract-OCR`, on the PATH, or wherever the
`TESSERACT_CMD` environment variable points. Everything runs on this computer;
nothing is sent online.

Put these files in `data/raw/` with exactly these names:

| File | What it is |
|---|---|
| `ABB_Price_List_Feb2026.xlsx` | ABB price list |
| `Schneider LV Price list Apr 2026.xlsx` | Schneider price list |
| `IEPCI Quotation .xlsx` | quotation template (note the space before `.xlsx`) |
| `RFQ_KBS-0147.pdf` | the Kestrel test RFQ |

## Run

```
streamlit run app.py                                  # the app
python -m pytest                                      # automated tests
python -m src.check_rfq_codes data/raw/RFQ_KBS-0147.pdf   # part-code check
python -m src.match_missing_codes data/raw/RFQ_KBS-0147.pdf
python -m src.generate_quotation data/raw/RFQ_KBS-0147.pdf --list-prices --out quote.xlsx
                                                      # Excel quotation using supplier list prices (INR)
python -m src.generate_quotation data/raw/RFQ_KBS-0147.pdf   # same, but rates left blank
python src/load_price_lists.py                        # rebuild data/processed/price_catalogue.csv
python -m src.extract_rfq data/raw/RFQ_KBS-0147.pdf   # show extracted lines + details (any file type)
python -m src.ocr_rfq scan.pdf --compare data/raw/RFQ_KBS-0147.pdf
                                                      # OCR accuracy against a known RFQ
```

Always run from the project root.

## How the pieces fit

```
RFQ file --extract_rfq.py--> line items + RFQ details (customer, RFQ no., ...)
  scans / photos --ocr_rfq.py---^  |
  emails / text --text_rfq.py---^  |
  OCR / typed codes --code_correction.py (checked against the price lists)
                                   |
price lists --load_price_lists.py--+--> one catalogue table (6,366 rows)
                                   |
        check_rfq_codes.py ........+--> per line: found / price / needs review
        match_missing_codes.py ....+--> ranked candidates for lines with no code
                                   |
         person reviews and approves rates in app.py
                                   |
        pricing.py ................+--> supplier list price (INR) per line, where clear
        generate_quotation.py -----+--> Excel draft from the IEPCI template
```

| File | Job |
|---|---|
| `app.py` | Streamlit app: upload, review, matching, catalogue, pricing, download |
| `src/extract_rfq.py` | Tables out of PDF/Word/Excel; header details; code-vs-note split |
| `src/ocr_rfq.py` | Scanned pages and photos: straighten, find table cells, read each cell with Tesseract |
| `src/text_rfq.py` | Email / text RFQs (.eml, .msg, .txt, pasted): attachments, pasted tables, item lines |
| `src/code_correction.py` | Fixes OCR misreads in part codes against the price lists; never changes typed codes |
| `src/load_price_lists.py` | ABB and Schneider layouts into one common table |
| `src/check_rfq_codes.py` | Part-code lookup with review flags |
| `src/match_missing_codes.py` | Spec-based candidates for lines without a code (air circuit breakers only) |
| `src/pricing.py` | Supplier list prices (INR, no discount); fills rates only where the price is clear |
| `src/generate_quotation.py` | Fills the template; adds rows beyond 17 lines; wraps long descriptions |
| `tests/test_kestrel_rfq.py` | Golden test for the Kestrel RFQ (30 checks) |
| `tests/test_ocr_and_text.py` | Scans made from the Kestrel RFQ must read the same; email and text formats |

### Scans and emails

A PDF page with no text is read with OCR. Every table cell is read on its own;
quantities and line numbers are read three times and only accepted when the
readings agree. Part codes are checked against the price lists: a code with
look-alike characters (O/0, I/1, S/5, `$`/S) or one wrong character is
corrected only when exactly one price-list code fits, and the note says what
was read. Anything uncertain gets `(OCR, check)` in the source column or a
note, and the app lists those lines first.

Email RFQs: an attached RFQ file is read first. Otherwise the text is read as
a pasted table, as labelled blocks (`Description:` / `Part No:` / `Qty:`), or
one item per line. A line with two different quantities gets none and the
note `check qty`. Codes the customer typed are never changed; if one is not in
the price lists, the closest one is mentioned in the note.

### What "clear price" means

A list price is filled in only when the RFQ has a complete part code, the code
exists in that supplier's list, and the list shows one price for it. Lines with
no code, an incomplete code (XX placeholder), a code that is not found, or no
published price are left blank and marked `REVIEW` in the quotation, so a
person prices them.

## Known limits

- Scans must be readable by eye: OCR has been tested on clean and poor
  (200 dpi, tilted, grainy) scans, photos and sideways pages of printed
  RFQs. Handwriting is not supported. Header details from a scan (names,
  phone numbers) are less reliable than the line items: check them.
- A scanned table without ruling lines is read from the word positions; this
  is less reliable than a ruled table.
- Email text is read with rules, not AI: items written as free sentences
  ("we also need a couple of contactors") are not picked up.
- "MATCHED - VERIFY SPECS" means the part code exists. It does not yet compare
  the catalogue specs with the RFQ description.
- `breaking_capacity` is a class letter for ABB (for example N) and kA for
  Schneider. Do not compare them directly.
- Prices are INR list price (MRP), before any discount or margin; the template
  adds 18% GST. The Kestrel RFQ asks for GBP, but this version works in INR only.
- "Amount in words", packing, freight, inspection, GSTN, IEC, inquiry type and
  sales representative are left blank in the quotation.
- The tests check exact prices from the current price lists. If the price lists
  are updated, expect those tests to need new expected values.
# IEPCI Quote Assistant

Reads a customer RFQ (PDF, Word or Excel), finds each item in the ABB and
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
python src/extract_rfq.py data/raw/RFQ_KBS-0147.pdf   # show extracted lines + details
```

Always run from the project root.

## How the pieces fit

```
RFQ file --extract_rfq.py--> line items + RFQ details (customer, RFQ no., ...)
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
| `src/extract_rfq.py` | Tables out of PDF/Word/Excel; header details; code-vs-note split; tries OCR / text layout / free text when there is no table |
| `src/ocr.py` | Local OCR (RapidOCR) for scanned PDF pages; cached per file and page |
| `src/layout.py` | Rebuilds table rows from text positions (OCR boxes, or PDF tables drawn without lines) |
| `src/parse_free_text.py` | Rule-based reading of items from emails / plain text (numbered lists, `5 x ...`, `Qty: 8`, labelled blocks, pasted tables) |
| `src/read_email.py` | Reads `.eml` / `.msg` / `.txt`: body, attachments and header details (sender, subject RFQ no., dates) |
| `src/load_price_lists.py` | ABB and Schneider layouts into one common table |
| `src/check_rfq_codes.py` | Part-code lookup with review flags |
| `src/match_missing_codes.py` | Spec-based candidates for lines without a code (air circuit breakers only) |
| `src/pricing.py` | Supplier list prices (INR, no discount); fills rates only where the price is clear |
| `src/generate_quotation.py` | Fills the template; adds rows beyond 17 lines; wraps long descriptions |
| `tests/test_kestrel_rfq.py` | Golden test for the Kestrel RFQ (30 checks) |
| `tests/test_ocr.py` | The Kestrel RFQ as an image-only scan must give the same lines (takes about a minute) |
| `tests/test_free_text.py`, `tests/test_email.py`, `tests/test_layout.py` | Free-text, email and no-table documents |

### What "clear price" means

A list price is filled in only when the RFQ has a complete part code, the code
exists in that supplier's list, and the list shows one price for it. Lines with
no code, an incomplete code (XX placeholder), a code that is not found, or no
published price are left blank and marked `REVIEW` in the quotation, so a
person prices them.

## Known limits

- RFQs without a table (emails, pasted text, prose documents) are read with
  rules, not AI: an item needs a quantity (`10 nos`, `5 x`, `Qty: 8`) or a
  numbered/bulleted line with product details. Unusual wording can be missed,
  so check the lines in the review table.
- Scanned PDFs are read with local OCR (RapidOCR, no internet or API key). It
  takes roughly 20-30 seconds a page, and handwriting is not read reliably. OCR
  can drop spaces inside descriptions; codes and quantities are what to check.
- `.xls` (old Excel) is not supported; save it as `.xlsx` first.
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
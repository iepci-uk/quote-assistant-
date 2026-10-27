"""Supplier list prices (INR) for RFQ lines.

These are the prices printed in the ABB and Schneider price lists (list price /
MRP). They are NOT IEPCI selling prices: no discount, margin, freight or
packing is applied. A person can still change every rate before the quotation
is issued.

A price is filled in only when it is clear: the RFQ gives a complete part code,
the code exists in that supplier's price list, and the list shows one price for
it. Everything else is left blank with a note saying why, so a person decides.
"""

import pandas as pd

from src.load_price_lists import make_key


def _has_value(value) -> bool:
    return pd.notna(value) and str(value).strip().lower() not in ("", "none", "nan")


def suggest_list_prices(lines: pd.DataFrame, catalogue: pd.DataFrame) -> pd.DataFrame:
    """One row per RFQ line: list_price_inr (number or NaN) and price_note."""
    results = []

    for line in lines.reset_index(drop=True).itertuples():
        code = str(getattr(line, "part_code", "") or "").strip()
        make = str(getattr(line, "make", "") or "").strip().upper()
        price, note = float("nan"), ""

        if not code:
            note = "no part code in the RFQ"
        elif "XX" in code.upper():
            note = "incomplete part code (XX placeholder)"
        else:
            hits = catalogue[catalogue["part_code_key"] == make_key(code)]
            if make:
                hits = hits[hits["supplier"].str.upper().str.contains(make, regex=False)]

            if hits.empty:
                note = "part code not found in the price list"
            elif hits["price_inr"].isna().any():
                note = f"no list price ({hits.iloc[0]['price_status']})"
            elif hits["price_inr"].nunique() > 1:
                note = "conflicting list prices for this code"
            else:
                price = float(hits["price_inr"].iloc[0])
                note = "list price (INR MRP)"
                if len(hits) > 1:
                    note += f", same price on {len(hits)} sheets"

        results.append({"line_no": line.line_no, "list_price_inr": price, "price_note": note})

    return pd.DataFrame(results)


def apply_list_prices(lines: pd.DataFrame, catalogue: pd.DataFrame) -> pd.DataFrame:
    """Use the supplier list price as the rate (and mark it approved) wherever
    a clear price exists and nobody has typed a rate yet.

    Lines without a clear price stay blank; the reason is added to code_note so
    it also shows in the quotation as 'REVIEW: ...'.
    """
    out = lines.copy().reset_index(drop=True)
    for column, default in (("unit_rate", None), ("price_approved", False), ("code_note", "")):
        if column not in out.columns:
            out[column] = default
    out["unit_rate"] = out["unit_rate"].astype(object)
    out["price_approved"] = out["price_approved"].astype(object)

    prices = suggest_list_prices(out, catalogue)
    for i, row in prices.iterrows():
        if _has_value(out.at[i, "unit_rate"]):
            continue                       # never overwrite a rate someone typed

        if pd.notna(row["list_price_inr"]):
            out.at[i, "unit_rate"] = row["list_price_inr"]
            out.at[i, "price_approved"] = True
        else:
            note = f"no list price filled: {row['price_note']}"
            existing = str(out.at[i, "code_note"]) if _has_value(out.at[i, "code_note"]) else ""
            if note not in existing:
                out.at[i, "code_note"] = "; ".join(x for x in (existing, note) if x)

    return out

"""Check part codes read by OCR (or typed in an email) against the price lists.

OCR mixes up characters that look alike: O and 0, I and 1, S and 5, B and 8.
A code read from a scan is therefore compared with the catalogue:

1. The code exists as read                    -> kept.
2. Exactly one catalogue code differs only in
   look-alike characters                       -> corrected, with a note.
3. Exactly one catalogue code is one character
   away (wrong, missing or extra character)    -> corrected, with a note.
4. Anything else (no match, or several)        -> kept as read; the code check
                                                  then sends it to a person.

Codes the customer typed (email, text) are never changed: a close catalogue
code is only mentioned in the note. Codes with an XX placeholder are never
touched.
"""

from collections import defaultdict

import pandas as pd

from src.load_price_lists import make_key

# Characters OCR confuses, grouped. Every member maps to the group's first one.
LOOK_ALIKES = ["0ODQ", "1IL", "5S", "8B", "2Z", "6G"]
CANONICAL = {char: group[0] for group in LOOK_ALIKES for char in group}

# Symbols OCR puts in place of a letter. make_key would drop them, losing a
# character, so they are swapped for the letter first.
SYMBOLS = str.maketrans({"$": "S", "|": "1", "§": "S"})


def canonical(key: str) -> str:
    return "".join(CANONICAL.get(char, char) for char in key)


class CodeIndex:
    """Catalogue part codes, searchable by supplier."""

    def __init__(self, catalogue: pd.DataFrame):
        self.printed = {}                              # (supplier, key) -> code as printed
        self.by_supplier = defaultdict(set)            # supplier -> keys
        self.by_canonical = defaultdict(set)           # (supplier, canonical key) -> keys
        for supplier, code, key in catalogue[["supplier", "part_code", "part_code_key"]].itertuples(index=False):
            if not key:
                continue
            self.printed.setdefault((supplier, key), str(code))
            self.by_supplier[supplier].add(key)
            self.by_canonical[(supplier, canonical(key))].add(key)
        self.all_keys = {key for keys in self.by_supplier.values() for key in keys}

    def suppliers(self, make: str):
        return [make] if make in self.by_supplier else list(self.by_supplier)

    def knows(self, key: str, make: str = "") -> bool:
        return any(key in self.by_supplier[s] for s in self.suppliers(make))

    def printed_code(self, key: str, make: str = "") -> str:
        for supplier in self.suppliers(make):
            if (supplier, key) in self.printed:
                return self.printed[(supplier, key)]
        return key

    def look_alike_matches(self, key: str, make: str = ""):
        found = set()
        for supplier in self.suppliers(make):
            found |= self.by_canonical.get((supplier, canonical(key)), set())
        return found

    def one_edit_matches(self, key: str, make: str = ""):
        """Codes one character away, after look-alike characters are evened out."""
        found, target = set(), canonical(key)
        for supplier in self.suppliers(make):
            for candidate in self.by_supplier[supplier]:
                if abs(len(candidate) - len(key)) <= 1 and one_edit_apart(target, canonical(candidate)):
                    found.add(candidate)
        return found


def one_edit_apart(a: str, b: str) -> bool:
    """True if a and b differ by exactly one changed, added or removed character."""
    if a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if b[:i] + b[i + 1:] == a:
            return True
    return False


def closest_code(code: str, make: str, index: CodeIndex):
    """Return (catalogue key or None, how it was found) for a code as read."""
    key = make_key(code)
    if not key:
        return None, ""
    if index.knows(key, make):
        return key, "exact"
    finders = [(index.look_alike_matches, "look-alike")]
    if "XX" not in key:          # placeholder codes: X positions must not move
        finders.append((index.one_edit_matches, "one character"))
    for finder, how in finders:
        matches = finder(key, make)
        if len(matches) == 1:
            return matches.pop(), how
        if len(matches) > 1:
            return None, "several"
    return None, ""


def add_note(existing: str, note: str) -> str:
    return f"{existing}; {note}" if existing else note


def correct_codes(lines: pd.DataFrame, index: CodeIndex, typed: bool = False) -> pd.DataFrame:
    """Fix OCR misreads in part codes (typed=False) or only suggest (typed=True)."""
    lines = lines.copy()
    for i, line in lines.iterrows():
        code = str(line["part_code"] or "")
        if not code:
            continue
        # A scanned '$' may be an S or a speck: try it both ways.
        readings = [code] if typed else list(dict.fromkeys([code.translate(SYMBOLS), code]))
        for reading in readings:
            key, how = closest_code(reading, line["make"], index)
            if how not in ("", "several"):
                break
        if how == "exact" and key == make_key(code):
            continue
        if how == "":
            if not typed:
                lines.at[i, "code_note"] = add_note(line["code_note"], "scanned code not in price list, check")
            continue
        if how == "several":
            lines.at[i, "code_note"] = add_note(line["code_note"], "code unclear, check")
            continue
        printed = index.printed_code(key, line["make"])
        if typed:
            lines.at[i, "code_note"] = add_note(line["code_note"], f"not in price list; closest is {printed}")
        else:
            lines.at[i, "part_code"] = printed
            lines.at[i, "code_note"] = add_note(line["code_note"], f"scan read {code}, corrected to {printed}")
    return lines

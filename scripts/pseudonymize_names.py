#!/usr/bin/env python3
"""Replace free-text names in a bulk-load source workbook with stable, salted
pseudonyms — keeping every non-name cell (code, DOB, sex, visit metrics, ...)
untouched.

Two human-named columns are touched:
    column H  - kid's full name     (NOMBRE DEL NIÑO/A)
    column J  - guardian/guardian   (NOMBRE DE LA MADRE)

Pseudonyms are a **deterministic** HMAC: HMAC_SALT(col, normalized_name).
That means the same person always hashes to the same pseudonym everywhere it
appears (kid and guardian rows), which preserves joins and makes re-running
against a second file consistent.

The pseudonymized file alone cannot be reversed — only the **key CSV**, which
stores the plaintext originals alongside their pseudonyms. Keep that file
separate/encrypted.

Usage:
    python pseudonymize_names.py <src.xlsx> <dst.xlsx> <key.csv>

Example:
    python pseudonymize_names.py tabulacion.xlsx tabulacion_pseudonymized.xlsx rekey.csv
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import sys

from openpyxl import load_workbook

KID_COL = 8      # H  - kid's full name
GUARDIAN_COL = 10  # J  - guardian name
HASH_LEN = 12

SALT = b"nutriacc-pseudonym-v1"


def pseudonym_for(col: int, original: str) -> str:
    normalized = original.strip().upper()
    claim = hmac.new(
        SALT,
        msg=f"{col}\x1f{normalized}".encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return claim.hexdigest().upper()[:HASH_LEN]


def pseudonymize(src, dst, key_path):
    book = load_workbook(src)
    sheet = book.active

    header_band = 4  # rows 1..4 are formula/metadata/column labels, not patients
    rows_seen = 0
    writes = 0
    key_rows = []

    for row in range(header_band + 1, sheet.max_row + 1):
        kid = sheet.cell(row=row, column=KID_COL).value
        guardian = sheet.cell(row=row, column=GUARDIAN_COL).value
        if not (kid or guardian):
            continue
        rows_seen += 1

        for col, entity in ((KID_COL, "kid"), (GUARDIAN_COL, "guardian")):
            value = sheet.cell(row=row, column=col).value
            if not value or not str(value).strip():
                continue
            original = str(value)
            pseudo = pseudonym_for(col, original)
            sheet.cell(row=row, column=col).value = pseudo
            writes += 1
            key_rows.append([col, entity, original, pseudo])

    book.save(dst)

    with open(key_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["column", "entity", "original", "pseudonym"])
        writer.writerows(key_rows)

    print(f"Rows with names: {rows_seen}")
    print(f"Pseudonym cells written: {writes}")
    print(f"Pseudonymized workbook -> {dst}")
    print(f"Re-match key -> {key_path} ({len(key_rows)} rows)")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Pseudonymize names in a source workbook (names only).")
    parser.add_argument("--src", default="scripts/tabulacion.xlsx")
    parser.add_argument("--dst", default="scripts/tabulacion_pseudonymized.xlsx")
    parser.add_argument("--key", default="scripts/rekey.csv")
    args = parser.parse_args(argv)
    pseudonymize(args.src, args.dst, args.key)


if __name__ == "__main__":
    sys.exit(main())

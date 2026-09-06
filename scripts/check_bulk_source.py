#!/usr/bin/env python3
"""Inspect a bulk-loading source sheet (tabulacion.xlsx) for quality issues that
would break the patient loader or corrupt records.

Report only: lists rows/fields that would be silently skipped, wrongly deduped,
or stored dirty. Does NOT touch the database.

Usage:
    python check_bulk_source.py <file.xlsx> <sheet> [--fail-on WARN|ERROR]

Exit code is 0 unless --fail-on=ERROR and an ERROR-severity issue is found, or
--fail-on=WARN and any issue appears. Severity model:

    ERROR   breaks dedupe or merges distinct patients (a `code` reused by two
            different people collapses into one record at load time).
    WARN    would be dropped or left dirty at load time.

CONTEXT.md mandates that age is derived from dob, so a missing/weird dob is a
WARN: the loader would store null Visit.age instead of a bad number.
"""
from __future__ import annotations

import argparse
import datetime as dt
import openpyxl

MAX_ROW = 200
MIN_YEAR = 1990


def read_sheet(path, sheet):
    wb = openpyxl.load_workbook(path, data_only=True)
    if sheet not in wb.sheetnames:
        raise SystemExit(f"sheet {sheet!r} not in {wb.sheetnames}")
    return wb[sheet]


def as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)
        print(f"  [ERROR] {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"  [WARN ] {msg}")

    def summary(self):
        print(f"\nTotal: {len(self.errors)} errors, {len(self.warnings)} warnings")


def check(path, sheet_name):
    sheet = read_sheet(path, sheet_name)
    rep = Report()
    codes = {}          # upper-cased code -> [rows]
    data_rows = 0
    distinct_codes = 0
    rows_with_metrics = 0
    today = dt.date.today()

    for row in range(3, MAX_ROW + 1):
        code = sheet.cell(row=row, column=7).value
        name = sheet.cell(row=row, column=8).value

        # Separator / legend rows have neither code nor name.
        if code is None and name is None:
            continue
        data_rows += 1

        if not code or str(code).strip() == "":
            rep.warn(f"row {row}: no code, only name={name!r} -> only loadable if a name+dob match exists")

        if code and str(code).strip():
            ckey = str(code).strip().upper()
            codes.setdefault(ckey, []).append(row)
            distinct_codes += 1

            d = as_date(sheet.cell(row=row, column=12).value)
            if d is None:
                rep.warn(f"row {row} ({ckey}): missing dob -> age can't be derived (Visit.age stays null)")
            elif d > today or d.year < MIN_YEAR:
                rep.error(f"row {row} ({ckey}): dob {d} out of range [{MIN_YEAR},{today.year}]")

        # Occurrence occupancy: does this row carry any weight/height value in the strip?
        has_metric = any(
            isinstance(sheet.cell(row=row, column=col).value, (int, float))
            for col in range(23, max(sheet.max_column + 1, 306))
        )
        if has_metric:
            rows_with_metrics += 1

    for key, rows in codes.items():
        if len(rows) > 1:
            rep.error(
                f"duplicate code {key!r} on rows {rows} — loader dedupes by code, "
                f"so these distinct patients get merged or the later row dropped"
            )
        if "_" in key or key.startswith("SHARED"):
            rep.warn(f"code {key!r} on rows {rows} looks shared/aggregated, not a single patient")

    rep.summary()
    print(f"\nScanned rows 3..{MAX_ROW}: {data_rows} data rows, {distinct_codes} distinct codes, "
          f"{rows_with_metrics} rows carrying a measurement.")
    return rep


def main():
    p = argparse.ArgumentParser(description="Inspect a bulk-load source sheet.")
    p.add_argument("file")
    p.add_argument("sheet", nargs="?", default="Nuevo NIMACABAJ2")
    p.add_argument("--fail-on", choices=["WARN", "ERROR"], default="ERROR",
                   help=" exit non-zero when any issue of this severity or higher appears")
    args = p.parse_args()

    report = check(args.file, args.sheet)
    if report.errors:
        return 1
    if args.fail_on == "WARN" and report.warnings:
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

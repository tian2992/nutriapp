#!/usr/bin/env python3
"""Replace the names in a workbook with stable pseudonyms, leaving every other
cell (code, DOB, sex, visit metrics, ...) untouched.

Which columns hold names is configuration, not a constant. Give targets
explicitly, take them from a loader profile, or let the script find them by
reading each sheet's header row — the default, because a sheet nobody
remembered to configure is how real names ship to a repository.

Usage:
    python scripts/pseudonymize_names.py --src book.xlsx --dst clean.xlsx --key rekey.csv
    python scripts/pseudonymize_names.py --target 'Nuevo NIMACABAJ2!H,J@5' --dry-run
    python scripts/pseudonymize_names.py --from-profile nimacabaj --from-profile qachuu_aloom

A target reads ``SHEET!COLUMNS@FIRST_ROW``: the sheet by name, the columns as
Excel letters or indices, and the first row holding a person rather than a
label. Drop ``@FIRST_ROW`` to have it detected from the header row.

Pseudonyms are a deterministic HMAC of the name, so the same person hashes to
the same pseudonym on every run and every sheet, which keeps joins working. The
pseudonymized file alone cannot be reversed — only the key CSV can, so keep it
out of the repository and encrypted.

The salt is read from $NUTRIAPP_PSEUDONYM_SALT. Without it the script falls back
to a salt committed in this file, which makes the pseudonyms guessable by
anyone holding the repository and a list of candidate names: it is
re-identification protection against a reader, not against an attacker. The
fallback exists because changing the salt changes every pseudonym, and the
loaded database matches children on the name it was given.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nutriapp"))

from anthrocalc import bulk_import, bulk_layout  # noqa: E402

HASH_LEN = 12
SALT_ENV = "NUTRIAPP_PSEUDONYM_SALT"
FALLBACK_SALT = b"nutriacc-pseudonym-v1"

# Words the promotores write where a name is not known yet. Hashing them would
# turn a legible "COMPLETAR" into a plausible-looking person.
PLACEHOLDERS = {
    "COMPLETAR",
    "POR COMPLETAR",
    "PENDIENTE",
    "PENDIENTE COMPLETAR",
    "SIN DATO",
    "SIN NOMBRE",
    "N/A",
    "NA",
    "-",
    "?",
}


@dataclass(frozen=True)
class Target:
    """The name columns of one sheet, and where its people start."""

    sheet: str
    columns: tuple[int, ...]
    first_row: int
    header_row: int
    origin: str

    def describe(self) -> str:
        columns = ", ".join(get_column_letter(col) for col in self.columns)
        return f"{self.sheet!r} columns {columns} from row {self.first_row} ({self.origin})"


def parse_target(spec: str) -> tuple[str, tuple[int, ...], int | None]:
    """``SHEET!H,J@5`` into its parts, with the row optional."""
    if "!" not in spec:
        raise ValueError(f"{spec!r} needs a sheet: write it as 'SHEET!H,J@5'")
    sheet, rest = spec.split("!", 1)

    first_row = None
    if "@" in rest:
        rest, row_text = rest.rsplit("@", 1)
        try:
            first_row = int(row_text)
        except ValueError as exc:
            raise ValueError(f"{spec!r}: {row_text!r} is not a row number") from exc

    columns = []
    for piece in rest.split(","):
        piece = piece.strip().upper()
        if not piece:
            continue
        try:
            columns.append(int(piece) if piece.isdigit() else column_index_from_string(piece))
        except ValueError as exc:
            raise ValueError(f"{spec!r}: {piece!r} is not a column") from exc
    if not columns:
        raise ValueError(f"{spec!r} names no columns")

    return sheet.strip(), tuple(columns), first_row


def targets_from_specs(workbook, specs: list[str]) -> list[Target]:
    targets = []
    for spec in specs:
        sheet_name, columns, first_row = parse_target(spec)
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"sheet {sheet_name!r} not in {workbook.sheetnames}")
        if first_row is None:
            header_row, _ = bulk_layout.find_header_row(workbook[sheet_name])
            first_row = header_row + 1
        targets.append(
            Target(sheet_name, columns, first_row, first_row - 1, f"--target {spec}")
        )
    return targets


def targets_from_profiles(workbook, references: list[str]) -> list[Target]:
    """Name columns taken from the profiles the loader reads the file with.

    Anything the loader treats as a name is a name, so the two stay in step
    without the columns being written down twice.
    """
    targets = []
    for reference in references:
        profile = bulk_import.load_profile(reference)
        if profile.sheet_name not in workbook.sheetnames:
            raise ValueError(
                f"profile {profile.name!r} reads sheet {profile.sheet_name!r}, "
                f"which is not in {workbook.sheetnames}"
            )
        columns = tuple(
            col
            for col in (profile.identity.name, profile.identity.mother_name)
            if col is not None
        )
        first_row = min(group.rows.start for group in profile.row_groups)
        targets.append(
            Target(
                profile.sheet_name,
                columns,
                first_row,
                profile.header_row,
                f"profile {profile.name!r}",
            )
        )
    return targets


def worksheets(workbook):
    """The sheets that hold cells. A workbook can also carry chart-only sheets."""
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        if hasattr(sheet, "cell"):
            yield sheet_name, sheet


def targets_by_detection(workbook) -> tuple[list[Target], list[str]]:
    """One target per sheet, from whatever its header row calls a name."""
    targets, warnings = [], []
    for sheet_name, sheet in worksheets(workbook):
        header_row, columns, _ = bulk_layout.name_columns(sheet)
        if not columns:
            warnings.append(
                f"{sheet_name!r}: no column is headed like a person's name. If it holds "
                f"names anyway, give it a --target."
            )
            continue
        targets.append(
            Target(sheet_name, tuple(columns), header_row + 1, header_row, "detected")
        )
    return targets, warnings


def uncovered_name_columns(workbook, targets: list[Target]) -> list[str]:
    """Name-looking columns nobody asked to pseudonymize.

    The failure this guards against has already happened once: the previous
    version of this script only touched the active sheet, and a second sheet of
    real names went to the repository untouched.
    """
    covered: dict[str, set[int]] = {}
    for target in targets:
        covered.setdefault(target.sheet, set()).update(target.columns)

    leaks = []
    for sheet_name, sheet in worksheets(workbook):
        _, columns, _ = bulk_layout.name_columns(sheet)
        missed = sorted(set(columns) - covered.get(sheet_name, set()))
        for col in missed:
            leaks.append(
                f"{sheet_name!r} column {get_column_letter(col)} is headed like a name "
                f"and is not being pseudonymized"
            )
    return leaks


def formula_cells_with_a_cached_value(workbook, values) -> int:
    """How many computed numbers saving this workbook would throw away.

    openpyxl writes a formula but not the value Excel last computed for it, so
    a save turns every calculated cell into a blank for anything reading the
    file afterwards. In this workbook round 39's and round 40's weights are
    ``=FX5/2.2`` conversions from the pounds column, and a plain save costs the
    loader ten measurements without a word about it.
    """
    lost = 0
    for sheet_name, sheet in worksheets(workbook):
        cached = values[sheet_name]
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    if cached.cell(row=cell.row, column=cell.column).value is not None:
                        lost += 1
    return lost


def read_salt() -> tuple[bytes, str]:
    from_env = os.environ.get(SALT_ENV)
    if from_env:
        return from_env.encode("utf-8"), f"${SALT_ENV}"
    return FALLBACK_SALT, f"the fallback salt in this file (set ${SALT_ENV} to override)"


def pseudonym_for(original: str, salt: bytes, column: int | None) -> str:
    """A stable pseudonym for one name.

    ``column`` scopes the hash: passing it reproduces the pseudonyms already in
    ``tabulacion_pseudonymized.xlsx`` and in the loaded database, at the cost of
    one person appearing as two pseudonyms when they are listed both as a child
    and as a guardian. Passing ``None`` gives them one pseudonym everywhere,
    which is what a fresh file should use.
    """
    normalized = original.strip().upper()
    message = normalized if column is None else f"{column}\x1f{normalized}"
    return hmac.new(salt, message.encode("utf-8"), hashlib.sha256).hexdigest().upper()[:HASH_LEN]


def pseudonymize(workbook, targets: list[Target], salt: bytes, scope: str) -> tuple[list[list], dict]:
    """Rewrite every targeted cell in place; return the key rows and a tally."""
    key_rows: dict[tuple, list] = {}
    counts = {"cells": 0, "placeholders": 0, "rows": 0}

    for target in targets:
        sheet = workbook[target.sheet]
        for row in range(target.first_row, sheet.max_row + 1):
            values = [sheet.cell(row=row, column=col).value for col in target.columns]
            if not any(value and str(value).strip() for value in values):
                continue
            counts["rows"] += 1

            for col, value in zip(target.columns, values):
                original = "" if value is None else str(value).strip()
                if not original:
                    continue
                if original.upper() in PLACEHOLDERS:
                    counts["placeholders"] += 1
                    continue

                column_scope = col if scope == "column" else None
                pseudonym = pseudonym_for(original, salt, column_scope)
                sheet.cell(row=row, column=col).value = pseudonym
                counts["cells"] += 1

                label = sheet.cell(row=target.header_row, column=col).value or ""
                key_rows.setdefault(
                    (column_scope, original.upper()),
                    [target.sheet, get_column_letter(col), str(label).strip(), original, pseudonym],
                )

    return list(key_rows.values()), counts


def run(args) -> int:
    workbook = load_workbook(args.src)
    values = load_workbook(args.src, data_only=True)

    at_risk = formula_cells_with_a_cached_value(workbook, values)
    if at_risk and not (args.flatten or args.keep_formulas):
        print(
            f"{args.src} has {at_risk} calculated cells whose values would be lost on "
            f"save, some of which the loader reads as weights.\n"
            f"  --flatten        replace the formulas with the numbers they produced\n"
            f"  --keep-formulas  save the formulas and accept the loss"
        )
        return 1
    if args.flatten:
        workbook = values

    targets = targets_from_specs(workbook, args.target)
    targets += targets_from_profiles(workbook, args.from_profile)
    detection_warnings: list[str] = []
    if not targets:
        targets, detection_warnings = targets_by_detection(workbook)
    if not targets:
        print("Nothing to pseudonymize: no targets given and none detected.")
        return 1

    salt, salt_source = read_salt()
    print(f"Salt: {salt_source}")
    print(f"Scope: {args.scope}")
    if at_risk:
        print(
            f"Formulas: {at_risk} calculated cells "
            + ("flattened to their values" if args.flatten else "kept, their values lost")
        )
    for target in targets:
        print(f"  {target.describe()}")
    for warning in detection_warnings + uncovered_name_columns(workbook, targets):
        print(f"  [warn] {warning}")

    key_rows, counts = pseudonymize(workbook, targets, salt, args.scope)

    print(
        f"\n{counts['rows']} rows with names, {counts['cells']} cells rewritten, "
        f"{len(key_rows)} distinct people, {counts['placeholders']} placeholders left alone."
    )

    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0

    workbook.save(args.dst)
    with open(args.key, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sheet", "column", "label", "original", "pseudonym"])
        writer.writerows(key_rows)

    print(f"Pseudonymized workbook -> {args.dst}")
    print(f"Re-match key -> {args.key} ({len(key_rows)} rows). Keep it out of the repository.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pseudonymize the names in a workbook, and nothing else.",
        epilog="With no --target and no --from-profile, every sheet is scanned for name columns.",
    )
    parser.add_argument("--src", default="scripts/tabulacion.xlsx")
    parser.add_argument("--dst", default="scripts/tabulacion_pseudonymized.xlsx")
    parser.add_argument("--key", default="scripts/rekey.csv")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="SHEET!COLS@ROW",
        help="Name columns to pseudonymize, e.g. 'Nuevo NIMACABAJ2!H,J@5'. Repeatable.",
    )
    parser.add_argument(
        "--from-profile",
        action="append",
        default=[],
        metavar="PROFILE",
        help=(
            "Take the name columns from a loader profile: a built-in name "
            f"({', '.join(sorted(bulk_import.PROFILES))}) or a path to a profile JSON. "
            "Repeatable."
        ),
    )
    parser.add_argument(
        "--scope",
        choices=("column", "person"),
        default="column",
        help=(
            "'column' reproduces the pseudonyms already in use; 'person' gives one "
            "pseudonym per name across every column, which links a woman listed both "
            "as a child and as a guardian. Default: column."
        ),
    )
    parser.add_argument(
        "--flatten",
        action="store_true",
        help=(
            "Write the numbers the formulas produced instead of the formulas. Keeps "
            "everything the loader reads; the output is data, not a working spreadsheet."
        ),
    )
    parser.add_argument(
        "--keep-formulas",
        action="store_true",
        help="Save the formulas and accept that their computed values are lost.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report the plan, write nothing.")
    args = parser.parse_args(argv)

    try:
        return run(args)
    except (OSError, ValueError, bulk_import.ProfileError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())

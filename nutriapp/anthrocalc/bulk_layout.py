"""Draft a ``SheetProfile`` by reading a worksheet's header row.

Transcribing a layout by hand is slow and the mistakes are quiet ones — a
height column off by one still parses, it just stores the wrong child's
numbers. This module does the first pass: it finds the header row, matches the
identity columns against the labels the promotores actually use, pairs weight
columns with the height column beside them, and looks above each pair for the
round's date.

What comes out is a **draft**, not a profile to load with. Detection cannot see
the things that are true of a file but written nowhere in it: which tables are
recaps of another table, a date that only exists in a caption, whether two
rosters are two communities. Every one of those is reported as a note for a
human to resolve, and the limitations are written up in
``docs/features/bulk_patients/profiles.md``.

Used by the ``inspect_xlsx_layout`` command and by the pseudonymizer, which
needs only the name columns.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

from .bulk_import import Block, IdentityColumns, RowGroup, SheetProfile

# How far below the header a run of empty name cells has to reach before it is
# read as the end of a roster rather than a gap inside one. The NIMACABAJ sheet
# has five blank rows in the middle of its main roster.
GROUP_GAP = 3

# A longer run than this means the roster is over and whatever follows is a
# summary panel, so scanning stops.
SCAN_STOP_GAP = 12

MAX_SCAN_ROWS = 500

# Beyond this a "name" is a sentence that spilled over from a neighbouring note.
MAX_NAME_LENGTH = 40


def normalize(value) -> str:
    """Upper-case, accent-free, single-spaced text for matching labels.

    Headers are typed by hand across a decade, so ``NIÑO`` and ``NINO``, or a
    label wrapped onto two lines, all have to land on the same string.
    """
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.upper().split())


def _matches(label: str, patterns: tuple[str, ...]) -> bool:
    return any(
        label == pattern[1:] if pattern.startswith("=") else pattern in label
        for pattern in patterns
    )


# Checked in order, so a narrower field claims its column before a broader one
# can: "CODIGO MADRE" has to be taken as the mother's code before "MADRE" makes
# it the mother's name. A leading "=" means the whole label must match.
IDENTITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mother_code", ("CODIGO MADRE", "CODIGO DE LA MADRE")),
    ("code", ("CODIGO",)),
    ("dob", ("FECHA DE NACIMIENTO", "F. NACIMIENTO", "F DE NACIMIENTO")),
    ("enrolled", ("FECHA DE INGRESO", "=INGRESO")),
    ("name", ("NOMBRE DEL NINO", "NOMBRE DE NINO", "NOMBRE DEL/A NINO", "NOMBRE DEL PACIENTE")),
    ("mother_name", ("NOMBRE DE LA MADRE", "MADRE", "RESPONSABLE", "ENCARGAD", "TUTOR")),
    ("community", ("COMUNIDAD",)),
    ("female", ("=F", "=NINA", "=SEXO F")),
    ("male", ("=M", "=NINO", "=SEXO M")),
)

WEIGHT_KG_PATTERNS = ("PESO KILO", "PESO (KG", "PESO KG", "=KG", "=KILOS", "=PESO")
WEIGHT_LB_PATTERNS = ("PESO (LB", "PESO LB", "=LIBRAS", "=LB")
HEIGHT_PATTERNS = ("ALTURA", "TALLA", "ESTATURA")
NOTES_PATTERNS = ("NOTAS", "OBSERVACION", "COMENTARIO")

# Any header that opens with FECHA is a visit date, except the two that name a
# different event. Sheets have called it "Fecha", "FECHA DE VISITA" and
# "FECHA JORNADA" in the same workbook.
NOT_A_VISIT_DATE = ("FECHA DE NACIMIENTO", "FECHA DE INGRESO", "FECHA DE NAC")


def is_visit_date(label: str) -> bool:
    return label.startswith("FECHA") and not any(
        label.startswith(other) for other in NOT_A_VISIT_DATE
    )

# "13va. Medición", "36 MEDICIÓN", "2da medicion" — the round number as the
# sheet writes it above the block.
ROUND_CAPTION = re.compile(r"(\d+)\s*(?:VA|RA|ERA|DA|TA|MA|A)?\.?\s*MEDICION")


@dataclass
class Note:
    """Something a human has to decide, or something worth double-checking."""

    level: str  # "found", "check" or "missing"
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


@dataclass
class Detection:
    profile: SheetProfile
    notes: list[Note] = field(default_factory=list)
    header_row: int = 0
    labels: dict[int, str] = field(default_factory=dict)

    def of_level(self, level: str) -> list[Note]:
        return [note for note in self.notes if note.level == level]


def header_labels(sheet, row: int, last_col: int) -> dict[int, str]:
    """Normalized, non-empty labels on one row, keyed by column index."""
    labels = {}
    for col in range(1, last_col + 1):
        label = normalize(sheet.cell(row=row, column=col).value)
        if label:
            labels[col] = label
    return labels


def find_header_row(sheet, search_rows: int = 12, last_col: int | None = None) -> tuple[int, int]:
    """The row that looks most like column labels, and how many it matched.

    Scored by how many of the identity and measurement labels it carries, so a
    title row or a row of dates never wins over the real header.
    """
    last_col = last_col or min(sheet.max_column, 400)
    all_patterns = [patterns for _, patterns in IDENTITY_PATTERNS]
    all_patterns += [WEIGHT_KG_PATTERNS, HEIGHT_PATTERNS]

    best_row, best_score = 1, 0
    for row in range(1, min(search_rows, sheet.max_row) + 1):
        labels = header_labels(sheet, row, last_col)
        score = sum(
            1
            for patterns in all_patterns
            if any(_matches(label, patterns) for label in labels.values())
        )
        if score > best_score:
            best_row, best_score = row, score
    return best_row, best_score


def detect_identity(labels: dict[int, str]) -> tuple[dict[str, int], list[Note]]:
    """Match the identity columns against the header labels, left to right."""
    found: dict[str, int] = {}
    claimed: set[int] = set()
    notes: list[Note] = []

    for field_name, patterns in IDENTITY_PATTERNS:
        for col in sorted(labels):
            if col in claimed or not _matches(labels[col], patterns):
                continue
            found[field_name] = col
            claimed.add(col)
            notes.append(Note("found", f"{field_name}: column {_ref(col)} {labels[col]!r}"))
            break

    for required in ("name", "dob"):
        if required not in found:
            notes.append(
                Note("missing", f"no column looks like the child's {required}; set it by hand")
            )
    if "female" not in found or "male" not in found:
        notes.append(
            Note(
                "missing",
                "no F/M sex flag columns; every child will load as X unless the "
                "profile names them",
            )
        )
    if "community" in found:
        notes.append(
            Note(
                "check",
                f"column {_ref(found['community'])} is headed COMUNIDAD, but in the "
                f"NIMACABAJ sheet that column holds spilled-over prose. Read it before "
                f"trusting it, and drop it from the profile if it is not clean.",
            )
        )
    return found, notes


def _ref(col: int) -> str:
    return f"{get_column_letter(col)}({col})"


def _columns_matching(labels: dict[int, str], patterns: tuple[str, ...]) -> list[int]:
    return sorted(col for col, label in labels.items() if _matches(label, patterns))


def _nearest(candidates: list[int], anchor: int, low: int, high: int) -> int | None:
    within = [col for col in candidates if low <= col <= high]
    return min(within, key=lambda col: abs(col - anchor)) if within else None


def _above(sheet, header_row: int, columns: range):
    """Every cell in the caption rows above a span, left to right, top to bottom."""
    for row in range(1, header_row):
        for col in columns:
            yield row, col, sheet.cell(row=row, column=col).value


def _round_date_above(sheet, header_row: int, own: range, rightward: range) -> tuple[int, int] | None:
    """The date cell belonging to a block, as ``(col, row)``.

    The block's own columns are searched first and the columns after it only
    then, because a date to the *left* of a block is the previous round's — the
    NIMACABAJ sheet puts the date over the second column of one round and two
    columns past the last of another, and reading leftwards silently gives
    every round its neighbour's date.
    """
    for columns in (own, rightward):
        for row, col, value in _above(sheet, header_row, columns):
            if isinstance(value, (dt.date, dt.datetime)):
                return col, row
    return None


def _round_number(sheet, header_row: int, own: range, rightward: range) -> str | None:
    for columns in (own, rightward):
        for _, _, value in _above(sheet, header_row, columns):
            match = ROUND_CAPTION.search(normalize(value))
            if match:
                return match.group(1)
    return None


def _date_column_owners(dates: list[int], anchors: list[int]) -> dict[int, int]:
    """Map each weight column to the ``FECHA`` column that introduces its block.

    A per-child date column sits immediately *before* the weights it belongs
    to, so it belongs to the first weight column to its right rather than the
    nearest one.
    """
    owners: dict[int, int] = {}
    for date_col in dates:
        to_the_right = [anchor for anchor in anchors if anchor > date_col]
        if to_the_right:
            owners.setdefault(to_the_right[0], date_col)
    return owners


def detect_blocks(sheet, header_row: int, labels: dict[int, str], first_col: int) -> tuple[list[Block], list[Note]]:
    """Pair each weight column with the height, date and notes around it.

    A kilogram column anchors a block, which reaches from just after the
    previous anchor to just before the next one. Within that, the height has to
    be to the right of the weight: pairing leftwards would marry the last
    column of one table to the first of another.
    """
    notes: list[Note] = []
    anchors = [col for col in _columns_matching(labels, WEIGHT_KG_PATTERNS) if col >= first_col]
    if not anchors:
        notes.append(
            Note("missing", "no column is headed like a weight, so no rounds were detected")
        )
        return [], notes

    heights = _columns_matching(labels, HEIGHT_PATTERNS)
    pounds = _columns_matching(labels, WEIGHT_LB_PATTERNS)
    dates = sorted(col for col, label in labels.items() if is_visit_date(label))
    notes_cols = _columns_matching(labels, NOTES_PATTERNS)
    last_col = max(labels) if labels else anchors[-1]
    date_owners = _date_column_owners(dates, anchors)

    blocks: list[Block] = []
    unpaired: list[int] = []
    used_numbers: set[str] = set()
    for index, anchor in enumerate(anchors):
        low = anchors[index - 1] + 1 if index else first_col
        high = anchors[index + 1] - 1 if index + 1 < len(anchors) else last_col

        height = _nearest(heights, anchor, anchor + 1, high)
        if height is None:
            unpaired.append(anchor)
            continue

        date_col = date_owners.get(anchor)
        if date_col is not None and date_col < low:
            date_col = None
        notes_col = _nearest(notes_cols, anchor, height + 1, high)
        pounds_col = _nearest(pounds, anchor, low, high)

        own = range(min(anchor, date_col or anchor, pounds_col or anchor), max(height, notes_col or height) + 1)
        rightward = range(own.stop, high + 1)
        round_date = _round_date_above(sheet, header_row, own, rightward)

        number = _round_number(sheet, header_row, own, rightward) or str(index + 1)
        if number in used_numbers:
            number = f"{number}@{get_column_letter(anchor)}"
        used_numbers.add(number)

        blocks.append(
            Block(
                number=number,
                weight_col=anchor,
                height_col=height,
                date_col=date_col,
                round_date_col=round_date[0] if round_date else None,
                round_date_row=round_date[1] if round_date else 2,
                weight_lb_col=pounds_col,
                notes_col=notes_col,
            )
        )
        if date_col is None and round_date is None:
            notes.append(
                Note(
                    "missing",
                    f"round {number} (weight {_ref(anchor)}) has no date column and no date "
                    f"above it; give it a fallback_date or it will yield no visits",
                )
            )

    if unpaired:
        notes.append(
            Note(
                "check",
                f"{len(unpaired)} weight column(s) have no height beside them and were "
                f"dropped: {', '.join(_ref(col) for col in unpaired[:8])}"
                + (" ..." if len(unpaired) > 8 else "")
                + ". A run of them means the sheet keeps weights and heights in two "
                "parallel tables, which detection cannot pair up; see profiles.md.",
            )
        )

    return blocks, notes


def detect_row_groups(sheet, header_row: int, name_col: int) -> tuple[list[RowGroup], list[Note]]:
    """Contiguous runs of rows carrying a name, split on the blank gaps."""
    notes: list[Note] = []
    occupied = []
    blanks = 0
    for row in range(header_row + 1, min(sheet.max_row, header_row + MAX_SCAN_ROWS) + 1):
        value = sheet.cell(row=row, column=name_col).value
        if value is None or not str(value).strip():
            blanks += 1
            if blanks >= SCAN_STOP_GAP and occupied:
                break
            continue
        blanks = 0
        occupied.append(row)
        text = str(value).strip()
        if len(text) > MAX_NAME_LENGTH:
            notes.append(
                Note(
                    "check",
                    f"row {row}'s name cell holds {len(text)} characters "
                    f"({text[:30]!r}...) — probably a caption, not a child",
                )
            )

    if not occupied:
        return [], [Note("missing", f"no rows below {header_row} carry a name")]

    groups: list[RowGroup] = []
    start = previous = occupied[0]
    for row in occupied[1:] + [None]:
        if row is None or row - previous > GROUP_GAP:
            groups.append(
                RowGroup(range(start, previous + 1), "", f"rows {start}-{previous}")
            )
            start = row
        previous = row

    notes.append(
        Note(
            "check",
            f"{len(groups)} roster(s) detected from blank-row gaps: "
            + ", ".join(f"{g.rows.start}-{g.rows.stop - 1}" for g in groups)
            + ". Community names are blank; fill them in.",
        )
    )
    return groups, notes


def detect(sheet, sheet_name: str | None = None, profile_name: str = "detected") -> Detection:
    """Draft a profile for one worksheet."""
    last_col = min(sheet.max_column, 400)
    header_row, score = find_header_row(sheet, last_col=last_col)
    labels = header_labels(sheet, header_row, last_col)

    notes = [Note("found", f"header row {header_row} ({score} label kinds matched)")]
    if score < 3:
        notes.append(
            Note(
                "check",
                f"row {header_row} matched only {score} known labels, so it may not be "
                f"the header at all",
            )
        )

    identity_cols, identity_notes = detect_identity(labels)
    notes += identity_notes

    first_col = max(identity_cols.values(), default=0) + 1
    blocks, block_notes = detect_blocks(sheet, header_row, labels, first_col)
    notes += block_notes

    groups: list[RowGroup] = []
    if "name" in identity_cols:
        groups, group_notes = detect_row_groups(sheet, header_row, identity_cols["name"])
        notes += group_notes

    notes.append(
        Note(
            "check",
            "detection reads one table per weight column. Recap tables that restate "
            "earlier rounds look exactly like new rounds, and would double-count; "
            "delete them from the draft unless they hold rounds the main strip lacks.",
        )
    )

    profile = SheetProfile(
        name=profile_name,
        sheet_name=sheet_name or sheet.title,
        header_row=header_row,
        identity=IdentityColumns(
            name=identity_cols.get("name", 1),
            dob=identity_cols.get("dob", 1),
            **{
                key: identity_cols.get(key)
                for key in ("code", "mother_code", "mother_name", "enrolled", "community", "female", "male")
            },
        ),
        row_groups=tuple(groups),
        blocks=tuple(blocks),
    )
    return Detection(profile=profile, notes=notes, header_row=header_row, labels=labels)


def name_columns(sheet) -> tuple[int, list[int], list[Note]]:
    """The header row and the columns holding a person's name.

    Split out for the pseudonymizer, which does not care where the weights are
    but must not miss a name column on a sheet nobody remembered to configure.
    """
    last_col = min(sheet.max_column, 400)
    header_row, _ = find_header_row(sheet, last_col=last_col)
    labels = header_labels(sheet, header_row, last_col)
    identity_cols, _ = detect_identity(labels)
    columns = sorted(
        col for key, col in identity_cols.items() if key in ("name", "mother_name")
    )
    notes = [
        Note("found", f"{sheet.title!r}: {labels.get(col, '')!r} in column {_ref(col)}")
        for col in columns
    ]
    if not columns:
        notes.append(Note("missing", f"{sheet.title!r}: no column is headed like a person's name"))
    return header_row, columns, notes


def compare(detected: SheetProfile, expected: SheetProfile) -> list[str]:
    """How a draft differs from a hand-written profile, field by field.

    This is how the detector's accuracy is measured against the one layout that
    has been verified by hand.
    """
    differences = []

    for key in IdentityColumns.__dataclass_fields__:
        got, want = getattr(detected.identity, key), getattr(expected.identity, key)
        if got != want:
            differences.append(f"identity.{key}: detected {got}, profile has {want}")

    if detected.header_row != expected.header_row:
        differences.append(
            f"header_row: detected {detected.header_row}, profile has {expected.header_row}"
        )

    got_rows = {(g.rows.start, g.rows.stop - 1) for g in detected.row_groups}
    want_rows = {(g.rows.start, g.rows.stop - 1) for g in expected.row_groups}
    if got_rows != want_rows:
        differences.append(f"row groups: detected {sorted(got_rows)}, profile has {sorted(want_rows)}")

    detected_pairs = {(b.weight_col, b.height_col): b for b in detected.blocks}
    expected_pairs = {(b.weight_col, b.height_col): b for b in expected.blocks}
    for pair in sorted(expected_pairs.keys() - detected_pairs.keys()):
        differences.append(
            f"round {expected_pairs[pair].number}: weight/height {pair} in the profile, not detected"
        )
    for pair in sorted(detected_pairs.keys() - expected_pairs.keys()):
        differences.append(f"detected a weight/height pair {pair} that the profile does not have")
    for pair in sorted(detected_pairs.keys() & expected_pairs.keys()):
        got, want = detected_pairs[pair], expected_pairs[pair]
        if got.date_col != want.date_col:
            differences.append(
                f"round {want.number}: date column detected {got.date_col}, profile has {want.date_col}"
            )
        if got.round_date_col != want.round_date_col:
            differences.append(
                f"round {want.number}: round-date cell detected "
                f"{got.round_date_col}/row {got.round_date_row}, profile has "
                f"{want.round_date_col}/row {want.round_date_row}"
            )

    return differences

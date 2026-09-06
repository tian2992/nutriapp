"""Read the NIMACABAJ field workbook into plain patient + occasion records.

The workbook is occurrence-based: one child per row, with measurement rounds
laid out left to right. This module collapses that back into one record per
child carrying a list of occasions, which the ``load_xlsx_patients`` command
turns into ``Patient`` / ``Visit`` / ``Metric`` rows.

Nothing here imports Django, so the parsing and validation rules can be tested
without a database.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import openpyxl

SHEET_NAME = "Nuevo NIMACABAJ2"

# --- Sheet geometry -------------------------------------------------------
#
# Row 4 holds the column labels; children start on row 5. Rows 1-3 carry the
# round dates and the "Nva. Medición" captions that span each block.

HEADER_ROW = 4
ROUND_DATE_ROW = 2
RECAP_DATE_ROW = 3

COL_COMMUNITY = 5  # E
COL_ENROLLED = 6  # F  "Fecha de ingreso"
COL_CODE = 7  # G  "CÓDIGO NIÑO(A)"
COL_NAME = 8  # H  "NOMBRE DEL NIÑO/A"
COL_MOTHER_CODE = 9  # I
COL_MOTHER_NAME = 10  # J
COL_DOB = 12  # L  "FECHA DE NACIMIENTO"
COL_DOB_FALLBACK = 13  # M  rows 55-60 keep the DOB under the "EDAD (MESES)" label
COL_FEMALE = 15  # O  flag column headed "F"
COL_MALE = 16  # P  flag column headed "M"

MAIN_COMMUNITY = "Nimacabaj"
DROPPED_COMMUNITY = "Nimacabaj-dropped"

GENDER_UNKNOWN = "X"

# Validation bounds, per docs/features/bulk_patients/loader.md §6.
WEIGHT_MIN_KG = 0.25
WEIGHT_MAX_KG = 120.0
HEIGHT_MIN_CM = 20.0
HEIGHT_MAX_CM = 220.0
DOB_MIN_YEAR = 1990
MAX_PLAUSIBLE_AGE_YEARS = 20

# No living child sits outside this band, and every measurement in the source
# falls between 13 and 28. It is what catches a weight recorded in the wrong
# unit, and the stray values that sit in the recap columns of rows belonging to
# children who were not yet born when those rounds took place.
MIN_POSSIBLE_BMI = 8.0
MAX_POSSIBLE_BMI = 40.0

POUNDS_PER_KG = 2.20462


@dataclass(frozen=True)
class RowGroup:
    """A contiguous run of children, and the community they belong to.

    The sheet stacks three rosters separated by blank and caption rows. Only
    the first names a community in column E, and even there the column is
    mostly blank or holds prose that spilled over from a neighbouring note, so
    the community is fixed per group rather than read per row.
    """

    rows: range
    community: str
    label: str


ROW_GROUPS = (
    RowGroup(range(5, 52), MAIN_COMMUNITY, "roster"),
    RowGroup(range(55, 61), DROPPED_COMMUNITY, "razón de finalización"),
    RowGroup(range(63, 69), DROPPED_COMMUNITY, "adolescentes"),
)


@dataclass(frozen=True)
class Block:
    """One measurement round's columns.

    Rounds come in three shapes. Early ones (13-24) share a single date held
    in ``round_date_col`` on row 2. Later ones (25-36) gain a leading per-child
    date column, so ``date_col`` wins where a child has one. The 2025-2026
    jornadas (38-40) went back to a shared date and added a pounds column
    beside the kilogram one.
    """

    number: str
    weight_col: int
    height_col: int
    date_col: int | None = None
    round_date_col: int | None = None
    round_date_row: int = ROUND_DATE_ROW
    fallback_date: dt.date | None = None
    weight_lb_col: int | None = None
    notes_col: int | None = None
    date_is_approximate: bool = False


# Rounds 1-12 and the "parcial" round live only in the recap tables at columns
# 199+ (weight) and 240+ (height); the main strip has no block for them. Their
# date sits on row 3 above the weight column.
RECAP_BLOCKS = tuple(
    Block(
        number=str(number),
        weight_col=weight_col,
        height_col=weight_col + 41,
        round_date_col=weight_col,
        round_date_row=RECAP_DATE_ROW,
        fallback_date=fallback,
        date_is_approximate=fallback is not None,
    )
    for number, weight_col, fallback in (
        ("1", 199, None),
        # Row 3 reads "OCTU14" here, the only round without a day. Mid-month
        # keeps the derived age within a fortnight of the truth.
        ("2", 200, dt.date(2014, 10, 15)),
        ("3", 201, None),
        ("4", 202, None),
        ("5", 203, None),
        ("6", 204, None),
        ("7", 205, None),
        ("8", 206, None),
        ("9", 207, None),
        ("10", 208, None),
        ("11", 209, None),
        ("12", 210, None),
        ("parcial", 211, None),
    )
)

# Rounds 28 and 37 are placeholders in the sheet ("NO HUBO MEDICION EN MARZO",
# "FALTAN LOS DATOS") and carry no values, so they have no block here.
STRIP_BLOCKS = (
    Block("13", 17, 18, round_date_col=18),
    Block("14", 23, 24, round_date_col=23),
    Block("15", 29, 30, round_date_col=29),
    Block("16", 35, 36, round_date_col=35),
    Block("17", 41, 42, round_date_col=41),
    Block("18", 47, 48, round_date_col=47),
    Block("19", 53, 54, round_date_col=54),
    # Round 20's caption says "FECHA:" but the date cell beside it was never
    # filled; the recap table records it as 2016-07-06.
    Block("20", 59, 60, fallback_date=dt.date(2016, 7, 6)),
    Block("21", 65, 66, round_date_col=66),
    Block("22", 71, 72, round_date_col=72),
    Block("23", 77, 78, round_date_col=78),
    Block("24", 83, 84, round_date_col=83),
    Block("25", 90, 91, date_col=89, round_date_col=90),
    Block("26", 96, 97, date_col=95, round_date_col=97),
    Block("27", 102, 103, date_col=101, round_date_col=103),
    Block("29", 109, 110, date_col=108, round_date_col=110),
    Block("30", 115, 116, date_col=114, round_date_col=116),
    Block("31", 121, 122, date_col=120, round_date_col=122),
    Block("32", 127, 128, date_col=126, round_date_col=128),
    Block("33", 133, 134, date_col=132, fallback_date=dt.date(2017, 8, 18)),
    Block("34", 139, 140, date_col=138, fallback_date=dt.date(2017, 9, 22)),
    Block("34-oct", 145, 146, date_col=144),
    Block("35", 151, 152, date_col=150, fallback_date=dt.date(2017, 11, 8)),
    # Row 3 reads "22/01/218" over this block, a typo for 2018.
    Block("36", 157, 158, date_col=156, fallback_date=dt.date(2018, 1, 22)),
    Block("38", 167, 168, round_date_col=169),
    Block("39", 172, 174, round_date_col=175, weight_lb_col=173, notes_col=178),
    Block("40", 179, 181, round_date_col=182, weight_lb_col=180, notes_col=185),
)

ALL_BLOCKS = RECAP_BLOCKS + STRIP_BLOCKS


@dataclass
class Occasion:
    """One measurement round for one child: a Visit plus its Metric."""

    block: str
    date: dt.date
    weight: float
    height: float
    notes: str | None = None
    date_is_approximate: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class PatientRecord:
    row: int
    code: str
    name: str
    gender: str
    dob: dt.date
    community: str
    group: str
    mother_name: str
    mother_code: str = ""
    enrolled_on: dt.date | None = None
    code_was_generated: bool = False
    occasions: list[Occasion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SkippedRow:
    row: int
    name: str
    reason: str


@dataclass
class ParseResult:
    patients: list[PatientRecord] = field(default_factory=list)
    skipped: list[SkippedRow] = field(default_factory=list)

    @property
    def occasion_count(self) -> int:
        return sum(len(p.occasions) for p in self.patients)


def generated_code(row: int) -> str:
    """Stand-in code for the children the sheet never assigned one to.

    Derived from the sheet row so a re-run produces the same code, and shaped
    unlike a real ``QARABNIM###`` so it reads as provisional.
    """
    return f"NIM-R{row:03d}"


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _flag(value) -> bool:
    """Whether a sex flag column is marked.

    The columns hold 1 where they apply and are empty otherwise, but a stray
    "x" or "X" would mean the same thing to the promotor filling it in.
    """
    if value is None:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    return _text(value) != ""


def read_gender(sheet, row: int) -> tuple[str, str | None]:
    """Return the child's sex and a warning when it could not be established."""
    female = _flag(sheet.cell(row=row, column=COL_FEMALE).value)
    male = _flag(sheet.cell(row=row, column=COL_MALE).value)
    if female and male:
        return GENDER_UNKNOWN, "both the F and M flags are set"
    if female:
        return "F", None
    if male:
        return "M", None
    return GENDER_UNKNOWN, "neither the F nor the M flag is set"


def _round_date(sheet, block: Block) -> dt.date | None:
    if block.round_date_col is None:
        return block.fallback_date
    cell = sheet.cell(row=block.round_date_row, column=block.round_date_col).value
    return _date(cell) or block.fallback_date


def read_occasion(
    sheet, row: int, block: Block, round_date: dt.date | None, dob: dt.date
) -> tuple[Occasion | None, str | None]:
    """Read one block for one child.

    Returns ``(None, None)`` for a round the child simply did not attend, and
    ``(None, reason)`` when there is something there but it cannot be trusted.
    """
    weight = _number(sheet.cell(row=row, column=block.weight_col).value)
    height = _number(sheet.cell(row=row, column=block.height_col).value)

    warnings: list[str] = []
    if weight is None and block.weight_lb_col is not None:
        pounds = _number(sheet.cell(row=row, column=block.weight_lb_col).value)
        if pounds is not None:
            weight = pounds / POUNDS_PER_KG
            warnings.append(f"weight converted from {pounds:g} lb")

    if weight is None and height is None:
        return None, None

    date = None
    if block.date_col is not None:
        date = _date(sheet.cell(row=row, column=block.date_col).value)
    approximate = block.date_is_approximate
    if date is None:
        date = round_date
        approximate = approximate or block.date_col is not None

    if date is None:
        return None, f"round {block.number}: no visit date on the row or the round"
    if date < dob:
        return None, f"round {block.number}: took place {date}, before the child was born"
    if weight is None:
        return None, f"round {block.number}: height {height:g} cm with no weight"
    if height is None:
        return None, f"round {block.number}: weight {weight:g} kg with no height"
    if not WEIGHT_MIN_KG < weight < WEIGHT_MAX_KG:
        return None, f"round {block.number}: weight {weight:g} outside {WEIGHT_MIN_KG}-{WEIGHT_MAX_KG} kg"
    if not HEIGHT_MIN_CM < height < HEIGHT_MAX_CM:
        return None, f"round {block.number}: height {height:g} outside {HEIGHT_MIN_CM}-{HEIGHT_MAX_CM} cm"

    bmi = weight / (height / 100) ** 2
    if not MIN_POSSIBLE_BMI < bmi < MAX_POSSIBLE_BMI:
        return None, (
            f"round {block.number}: {weight:g} kg at {height:g} cm is a BMI of {bmi:.0f}, "
            f"which is not a real body; check the units on the source cell"
        )

    if (date - dob).days / 365.25 > MAX_PLAUSIBLE_AGE_YEARS:
        warnings.append(f"child is over {MAX_PLAUSIBLE_AGE_YEARS} at this visit")

    notes = _text(sheet.cell(row=row, column=block.notes_col).value) if block.notes_col else ""

    return (
        Occasion(
            block=block.number,
            date=date,
            weight=weight,
            height=height,
            notes=notes or None,
            date_is_approximate=approximate,
            warnings=warnings,
        ),
        None,
    )


def read_patient(sheet, row: int, group: RowGroup, today: dt.date) -> tuple[PatientRecord | None, SkippedRow | None]:
    name = _text(sheet.cell(row=row, column=COL_NAME).value)
    if not name:
        return None, None

    dob = _date(sheet.cell(row=row, column=COL_DOB).value) or _date(
        sheet.cell(row=row, column=COL_DOB_FALLBACK).value
    )
    if dob is None:
        return None, SkippedRow(row, name, "no date of birth, so no age can be derived")
    if dob > today or dob.year < DOB_MIN_YEAR:
        return None, SkippedRow(row, name, f"date of birth {dob} is outside {DOB_MIN_YEAR}-{today.year}")

    warnings: list[str] = []
    gender, gender_warning = read_gender(sheet, row)
    if gender_warning:
        warnings.append(f"{gender_warning}; stored as {GENDER_UNKNOWN} pending confirmation")

    code = _text(sheet.cell(row=row, column=COL_CODE).value)
    code_was_generated = not code
    if code_was_generated:
        code = generated_code(row)

    mother_name = _text(sheet.cell(row=row, column=COL_MOTHER_NAME).value)
    if not mother_name:
        mother_name = f"Sin responsable ({code})"
        warnings.append("no guardian name; the family is labelled from the child's code")

    patient = PatientRecord(
        row=row,
        code=code,
        name=name,
        gender=gender,
        dob=dob,
        community=group.community,
        group=group.label,
        mother_name=mother_name,
        mother_code=_text(sheet.cell(row=row, column=COL_MOTHER_CODE).value),
        enrolled_on=_date(sheet.cell(row=row, column=COL_ENROLLED).value),
        code_was_generated=code_was_generated,
    )

    seen_dates: dict[dt.date, str] = {}
    for block in ALL_BLOCKS:
        occasion, reason = read_occasion(sheet, row, block, _round_date(sheet, block), dob)
        if reason:
            warnings.append(reason)
            continue
        if occasion is None:
            continue
        if occasion.date in seen_dates:
            warnings.append(
                f"round {block.number}: same date as round {seen_dates[occasion.date]} ({occasion.date}); kept the first"
            )
            continue
        seen_dates[occasion.date] = block.number
        patient.occasions.append(occasion)

    patient.occasions.sort(key=lambda o: o.date)
    patient.warnings.extend(warnings)
    return patient, None


def parse_sheet(sheet, today: dt.date | None = None) -> ParseResult:
    today = today or dt.date.today()
    result = ParseResult()
    for group in ROW_GROUPS:
        for row in group.rows:
            patient, skipped = read_patient(sheet, row, group, today)
            if patient is not None:
                result.patients.append(patient)
            elif skipped is not None:
                result.skipped.append(skipped)
    return result


def parse_workbook(path, sheet_name: str = SHEET_NAME, today: dt.date | None = None) -> ParseResult:
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"sheet {sheet_name!r} not in {workbook.sheetnames}")
    return parse_sheet(workbook[sheet_name], today=today)

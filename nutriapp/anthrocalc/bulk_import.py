"""Read a field workbook into plain patient + occasion records.

The workbooks are occurrence-based: one child per row, with measurement rounds
laid out left to right. This module collapses that back into one record per
child carrying a list of occasions, which the ``load_xlsx_patients`` command
turns into ``Patient`` / ``Visit`` / ``Metric`` rows.

Where a given file puts its columns is not baked into the reading code. A
``SheetProfile`` names every column the parser touches, and the parser takes one
as an argument, so a new file is a new profile rather than a new parser. Two
profiles ship built in (``NIMACABAJ``, ``QACHUU_ALOOM``) and a profile can also
be read from JSON on disk. ``bulk_layout`` drafts one by reading the header row.

Nothing here imports Django, so the parsing and validation rules can be tested
without a database, and the pseudonymizer in ``scripts/`` can share the column
map with the loader.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

GENDER_UNKNOWN = "X"

# Validation bounds, per docs/features/bulk_patients/loader.md. These are
# properties of children rather than of any one spreadsheet, so they stay
# global: a profile can move a column, not widen what counts as a body.
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


class ProfileError(ValueError):
    """A profile that cannot be trusted to read a sheet correctly."""


def column_index(value) -> int:
    """A 1-based column index from either an index or an Excel letter.

    Profiles on disk are written in letters, because that is what someone
    checking them against the spreadsheet can see in the column header.
    """
    if isinstance(value, int):
        return value
    text = str(value).strip().upper()
    return int(text) if text.isdigit() else column_index_from_string(text)


def _optional_index(value) -> int | None:
    return None if value in (None, "") else column_index(value)


def _letter(index: int | None) -> str | None:
    return None if index is None else get_column_letter(index)


@dataclass(frozen=True)
class IdentityColumns:
    """Where the per-child fields sit on a row.

    Only ``name`` and ``dob`` are required; a file that has no code column, no
    guardian and no sex flags still yields patients, just with more warnings.
    """

    name: int
    dob: int
    code: int | None = None
    dob_fallback: int | None = None
    female: int | None = None
    male: int | None = None
    mother_name: int | None = None
    mother_code: int | None = None
    enrolled: int | None = None
    community: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> IdentityColumns:
        unknown = set(data) - {f for f in cls.__dataclass_fields__}
        if unknown:
            raise ProfileError(f"unknown identity columns: {sorted(unknown)}")
        if "name" not in data or "dob" not in data:
            raise ProfileError("identity needs at least a 'name' and a 'dob' column")
        return cls(
            name=column_index(data["name"]),
            dob=column_index(data["dob"]),
            **{
                key: _optional_index(data.get(key))
                for key in cls.__dataclass_fields__
                if key not in ("name", "dob")
            },
        )

    def to_dict(self) -> dict:
        return {
            key: _letter(getattr(self, key))
            for key in self.__dataclass_fields__
            if getattr(self, key) is not None
        }


@dataclass(frozen=True)
class RowGroup:
    """A contiguous run of children, and the community they belong to.

    A sheet often stacks several rosters separated by blank and caption rows,
    and the community is rarely legible per row: in the NIMACABAJ sheet the
    column meant for it is mostly blank or holds prose that spilled over from a
    neighbouring note. So the community is fixed per group, unless
    ``IdentityColumns.community`` is set and the cell has something in it.
    """

    rows: range
    community: str
    label: str

    @classmethod
    def from_dict(cls, data: dict) -> RowGroup:
        try:
            first, last = int(data["first_row"]), int(data["last_row"])
        except KeyError as exc:
            raise ProfileError(f"row group is missing {exc}") from exc
        return cls(
            rows=range(first, last + 1),
            community=data.get("community", ""),
            label=data.get("label", f"rows {first}-{last}"),
        )

    def to_dict(self) -> dict:
        return {
            "first_row": self.rows.start,
            "last_row": self.rows.stop - 1,
            "community": self.community,
            "label": self.label,
        }


@dataclass(frozen=True)
class Block:
    """One measurement round's columns.

    A round needs a weight, a height and a date. The date can come from three
    places, in falling order of trust: ``date_col``, a per-child cell on the
    row; ``round_date_col``, one cell on ``round_date_row`` above the block that
    covers every child; or ``fallback_date``, hard-coded here because the sheet
    records the date somewhere no code can reach — a caption, another table, or
    nowhere at all.

    ``weight_lb_col`` is read only when the kilogram cell is empty, and
    ``notes_col`` lands on ``Visit.notes``.
    """

    number: str
    weight_col: int
    height_col: int
    date_col: int | None = None
    round_date_col: int | None = None
    round_date_row: int = 2
    fallback_date: dt.date | None = None
    weight_lb_col: int | None = None
    notes_col: int | None = None
    date_is_approximate: bool = False

    _KEYS = (
        "number",
        "weight",
        "height",
        "date",
        "round_date",
        "round_date_row",
        "fallback_date",
        "weight_lb",
        "notes",
        "date_is_approximate",
    )

    @classmethod
    def from_dict(cls, data: dict) -> Block:
        unknown = set(data) - set(cls._KEYS)
        if unknown:
            raise ProfileError(f"unknown block keys: {sorted(unknown)}")
        try:
            fallback = data.get("fallback_date")
            return cls(
                number=str(data["number"]),
                weight_col=column_index(data["weight"]),
                height_col=column_index(data["height"]),
                date_col=_optional_index(data.get("date")),
                round_date_col=_optional_index(data.get("round_date")),
                round_date_row=int(data.get("round_date_row", 2)),
                fallback_date=dt.date.fromisoformat(fallback) if fallback else None,
                weight_lb_col=_optional_index(data.get("weight_lb")),
                notes_col=_optional_index(data.get("notes")),
                date_is_approximate=bool(data.get("date_is_approximate", False)),
            )
        except KeyError as exc:
            raise ProfileError(f"block {data.get('number')!r} is missing {exc}") from exc

    def to_dict(self) -> dict:
        out = {
            "number": self.number,
            "weight": _letter(self.weight_col),
            "height": _letter(self.height_col),
        }
        if self.date_col is not None:
            out["date"] = _letter(self.date_col)
        if self.round_date_col is not None:
            out["round_date"] = _letter(self.round_date_col)
            out["round_date_row"] = self.round_date_row
        if self.fallback_date is not None:
            out["fallback_date"] = self.fallback_date.isoformat()
        if self.weight_lb_col is not None:
            out["weight_lb"] = _letter(self.weight_lb_col)
        if self.notes_col is not None:
            out["notes"] = _letter(self.notes_col)
        if self.date_is_approximate:
            out["date_is_approximate"] = True
        return out


@dataclass(frozen=True)
class SheetProfile:
    """Everything the parser needs to know about one worksheet's layout."""

    name: str
    sheet_name: str
    identity: IdentityColumns
    row_groups: tuple[RowGroup, ...]
    blocks: tuple[Block, ...]
    header_row: int = 4
    code_prefix: str = "GEN"

    def generated_code(self, row: int) -> str:
        """Stand-in code for a child the sheet never assigned one to.

        Derived from the sheet row so a re-run produces the same code, and
        shaped unlike a real ``QARABNIM###`` so it reads as provisional.
        """
        return f"{self.code_prefix}-R{row:03d}"

    def problems(self) -> list[str]:
        """Ways this profile would silently misread a sheet.

        Every one of these has been an actual mistake at some point while
        transcribing a layout by hand, and each produces wrong records rather
        than a crash, so they are checked before the profile is ever used.
        """
        found = []

        numbers = [block.number for block in self.blocks]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            found.append(f"blocks share a number: {duplicates}")

        claimed: dict[int, str] = {}
        for block in self.blocks:
            for role, col in (("weight", block.weight_col), ("height", block.height_col)):
                if col in claimed:
                    found.append(
                        f"block {block.number}'s {role} column {_letter(col)} is already "
                        f"the {claimed[col]}"
                    )
                claimed[col] = f"{role} of block {block.number}"

        for block in self.blocks:
            if not (block.date_col or block.round_date_col or block.fallback_date):
                found.append(
                    f"block {block.number} has no date column and no fallback, "
                    f"so it can never yield a visit"
                )

        seen_rows: dict[int, str] = {}
        for group in self.row_groups:
            if not group.rows:
                found.append(f"row group {group.label!r} is empty")
            for row in group.rows:
                if row in seen_rows:
                    found.append(
                        f"row {row} is in both {seen_rows[row]!r} and {group.label!r}, "
                        f"so that child would load twice"
                    )
                seen_rows[row] = group.label
            if group.rows and group.rows.start <= self.header_row:
                found.append(
                    f"row group {group.label!r} starts at row {group.rows.start}, "
                    f"on or above the header row {self.header_row}"
                )

        return found

    def validated(self) -> SheetProfile:
        problems = self.problems()
        if problems:
            raise ProfileError(
                f"profile {self.name!r} is unusable:\n  " + "\n  ".join(problems)
            )
        return self

    @classmethod
    def from_dict(cls, data: dict) -> SheetProfile:
        try:
            profile = cls(
                name=data.get("name", "unnamed"),
                sheet_name=data["sheet_name"],
                identity=IdentityColumns.from_dict(data["identity"]),
                row_groups=tuple(RowGroup.from_dict(g) for g in data["row_groups"]),
                blocks=tuple(Block.from_dict(b) for b in data["blocks"]),
                header_row=int(data.get("header_row", 4)),
                code_prefix=data.get("code_prefix", "GEN"),
            )
        except KeyError as exc:
            raise ProfileError(f"profile is missing {exc}") from exc
        return profile.validated()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sheet_name": self.sheet_name,
            "header_row": self.header_row,
            "code_prefix": self.code_prefix,
            "identity": self.identity.to_dict(),
            "row_groups": [group.to_dict() for group in self.row_groups],
            "blocks": [block.to_dict() for block in self.blocks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"


# --- The NIMACABAJ workbook -----------------------------------------------
#
# Row 4 holds the column labels; children start on row 5. Rows 1-3 carry the
# round dates and the "Nva. Medición" captions that span each block. The full
# reasoning behind every index is in docs/features/bulk_patients/index.md.

NIMACABAJ_DATE_ROW = 2
NIMACABAJ_RECAP_DATE_ROW = 3

MAIN_COMMUNITY = "Nimacabaj"
DROPPED_COMMUNITY = "Nimacabaj-dropped"

# Rounds 1-12 and the "parcial" round live only in the recap tables at columns
# 199+ (weight) and 240+ (height); the main strip has no block for them. Their
# date sits on row 3 above the weight column.
_NIMACABAJ_RECAP_BLOCKS = tuple(
    Block(
        number=str(number),
        weight_col=weight_col,
        height_col=weight_col + 41,
        round_date_col=weight_col,
        round_date_row=NIMACABAJ_RECAP_DATE_ROW,
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
_NIMACABAJ_STRIP_BLOCKS = (
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

NIMACABAJ = SheetProfile(
    name="nimacabaj",
    sheet_name="Nuevo NIMACABAJ2",
    header_row=4,
    code_prefix="NIM",
    identity=IdentityColumns(
        code=7,  # G  "CÓDIGO NIÑO(A)"
        name=8,  # H  "NOMBRE DEL NIÑO/A"
        mother_code=9,  # I
        mother_name=10,  # J
        dob=12,  # L  "FECHA DE NACIMIENTO"
        dob_fallback=13,  # M  rows 55-60 keep the DOB under the "EDAD (MESES)" label
        female=15,  # O
        male=16,  # P
        enrolled=6,  # F  "Fecha de ingreso"
        # Column E is headed COMUNIDAD but holds prose on six rows, so the
        # community comes from the row group instead.
        community=None,
    ),
    row_groups=(
        RowGroup(range(5, 52), MAIN_COMMUNITY, "roster"),
        RowGroup(range(55, 61), DROPPED_COMMUNITY, "razón de finalización"),
        RowGroup(range(63, 69), DROPPED_COMMUNITY, "adolescentes"),
    ),
    blocks=_NIMACABAJ_RECAP_BLOCKS + _NIMACABAJ_STRIP_BLOCKS,
).validated()


# --- The Qachuu Aloom jornada ----------------------------------------------
#
# A flat sheet in the same workbook: one jornada, one row per child, a single
# measurement block. It exists here to keep the profile mechanism honest — it is
# the shape a new file is most likely to arrive in — and is not loaded, because
# the sheet still holds real names (see docs/features/bulk_patients/index.md).

QACHUU_ALOOM = SheetProfile(
    name="qachuu_aloom",
    sheet_name="Jornada en Qachuu Aloom",
    header_row=4,
    code_prefix="QA",
    identity=IdentityColumns(
        name=2,  # B
        mother_name=3,  # C
        dob=5,  # E
        female=8,  # H
        male=9,  # I
    ),
    # Rows 18 onwards hold a totals row and a summary panel that reuses columns
    # J-L, which are the weight and height columns.
    row_groups=(RowGroup(range(5, 18), "Varias Comunidades", "jornada 2025-06-05"),),
    blocks=(
        Block(
            "36",
            weight_col=11,  # K  "Kg"
            height_col=12,  # L  "Talla (cms)"
            weight_lb_col=10,  # J  "Libras"
            round_date_col=13,  # M2 "FECHA JORNADA"
        ),
    ),
).validated()


PROFILES = {profile.name: profile for profile in (NIMACABAJ, QACHUU_ALOOM)}
DEFAULT_PROFILE = NIMACABAJ


def load_profile(reference: str | Path) -> SheetProfile:
    """A built-in profile by name, or one read from a JSON file."""
    key = str(reference)
    if key in PROFILES:
        return PROFILES[key]
    path = Path(reference)
    if not path.exists():
        raise ProfileError(
            f"{key!r} is neither a built-in profile ({', '.join(sorted(PROFILES))}) "
            f"nor a file that exists"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"{path} is not valid JSON: {exc}") from exc
    return SheetProfile.from_dict(data)


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


def _cell(sheet, row: int, col: int | None):
    return None if col is None else sheet.cell(row=row, column=col).value


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


def read_gender(sheet, row: int, identity: IdentityColumns) -> tuple[str, str | None]:
    """Return the child's sex and a warning when it could not be established."""
    if identity.female is None and identity.male is None:
        return GENDER_UNKNOWN, "the sheet has no sex column"
    female = _flag(_cell(sheet, row, identity.female))
    male = _flag(_cell(sheet, row, identity.male))
    if female and male:
        return GENDER_UNKNOWN, "both the F and M flags are set"
    if female:
        return "F", None
    if male:
        return "M", None
    return GENDER_UNKNOWN, "neither the F nor the M flag is set"


def round_date(sheet, block: Block) -> dt.date | None:
    """The date the whole round shares, from above the block or hard-coded."""
    if block.round_date_col is None:
        return block.fallback_date
    cell = sheet.cell(row=block.round_date_row, column=block.round_date_col).value
    return _date(cell) or block.fallback_date


def read_occasion(
    sheet, row: int, block: Block, shared_date: dt.date | None, dob: dt.date
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

    date = _date(_cell(sheet, row, block.date_col))
    approximate = block.date_is_approximate
    if date is None:
        date = shared_date
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

    notes = _text(_cell(sheet, row, block.notes_col))

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


def read_patient(
    sheet, row: int, group: RowGroup, profile: SheetProfile, today: dt.date
) -> tuple[PatientRecord | None, SkippedRow | None]:
    identity = profile.identity
    name = _text(_cell(sheet, row, identity.name))
    if not name:
        return None, None

    dob = _date(_cell(sheet, row, identity.dob)) or _date(
        _cell(sheet, row, identity.dob_fallback)
    )
    if dob is None:
        return None, SkippedRow(row, name, "no date of birth, so no age can be derived")
    if dob > today or dob.year < DOB_MIN_YEAR:
        return None, SkippedRow(row, name, f"date of birth {dob} is outside {DOB_MIN_YEAR}-{today.year}")

    warnings: list[str] = []
    gender, gender_warning = read_gender(sheet, row, identity)
    if gender_warning:
        warnings.append(f"{gender_warning}; stored as {GENDER_UNKNOWN} pending confirmation")

    code = _text(_cell(sheet, row, identity.code))
    code_was_generated = not code
    if code_was_generated:
        code = profile.generated_code(row)

    mother_name = _text(_cell(sheet, row, identity.mother_name))
    if not mother_name:
        mother_name = f"Sin responsable ({code})"
        warnings.append("no guardian name; the family is labelled from the child's code")

    patient = PatientRecord(
        row=row,
        code=code,
        name=name,
        gender=gender,
        dob=dob,
        community=_text(_cell(sheet, row, identity.community)) or group.community,
        group=group.label,
        mother_name=mother_name,
        mother_code=_text(_cell(sheet, row, identity.mother_code)),
        enrolled_on=_date(_cell(sheet, row, identity.enrolled)),
        code_was_generated=code_was_generated,
    )

    seen_dates: dict[dt.date, str] = {}
    for block in profile.blocks:
        occasion, reason = read_occasion(sheet, row, block, round_date(sheet, block), dob)
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


def parse_sheet(
    sheet, profile: SheetProfile = DEFAULT_PROFILE, today: dt.date | None = None
) -> ParseResult:
    today = today or dt.date.today()
    result = ParseResult()
    for group in profile.row_groups:
        for row in group.rows:
            patient, skipped = read_patient(sheet, row, group, profile, today)
            if patient is not None:
                result.patients.append(patient)
            elif skipped is not None:
                result.skipped.append(skipped)
    return result


def open_sheet(path, sheet_name: str):
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    if sheet_name not in workbook.sheetnames:
        raise ValueError(f"sheet {sheet_name!r} not in {workbook.sheetnames}")
    return workbook[sheet_name]


def parse_workbook(
    path,
    profile: SheetProfile = DEFAULT_PROFILE,
    sheet_name: str | None = None,
    today: dt.date | None = None,
) -> ParseResult:
    """Parse ``path`` with ``profile``, optionally against a different worksheet.

    ``sheet_name`` is for the case where the same layout was copied into a
    second tab; anything more than the tab name differing needs its own profile.
    """
    if sheet_name and sheet_name != profile.sheet_name:
        profile = replace(profile, sheet_name=sheet_name)
    return parse_sheet(open_sheet(path, profile.sheet_name), profile, today=today)

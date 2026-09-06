"""Put the real names back, from the key a pseudonymization run wrote.

    ./manage.py rekey_patients --rekey scripts/rekey.csv --dry-run
    ./manage.py rekey_patients --rekey scripts/rekey.csv --rekey scripts/rekey_qachuu.csv

Only the ``original`` and ``pseudonym`` columns of the key are read. The rest
of the file says where a name was *found*, which is not where it has to be
*applied*: the same woman is a guardian on one sheet and appears in a child
column on another, and a key row labelled "kid" still has to rekey a
``Family``. So every pseudonym is looked for in every name field.

Running it twice is harmless — a name that has already been restored is not a
pseudonym any more and simply does not match.
"""

import csv
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from anthrocalc.models import Family, Patient

REQUIRED_COLUMNS = ("original", "pseudonym")

# A pseudonym is 12 hex characters, so one whose only letter is an E reads as
# scientific notation to a spreadsheet: open the key in Excel, save it, and
# "309165531E20" comes back as "3.09165531E+028".
MANGLED = re.compile(r"^(\d)\.(\d+)E\+?(\d+)$", re.IGNORECASE)
PSEUDONYM_LENGTH = 12

# Past this a spreadsheet cannot hold the number at all and leaves the cell as
# text, so an exponent above it never came from a mangled pseudonym.
MAX_FLOAT_EXPONENT = 308


def unmangle(text: str) -> str:
    """The pseudonym a spreadsheet turned into a number, or the text unchanged.

    ``309165531E20`` reads as 3.09165531 × 10²⁸ and comes back written that
    way. The digits survive, so the original is the mantissa followed by an
    exponent reduced by however many digits moved in front of the decimal
    point, zero-padded back out to the length of a pseudonym.
    """
    match = MANGLED.match(text)
    if not match:
        return text
    lead, rest, exponent = match.groups()
    if int(exponent) > MAX_FLOAT_EXPONENT:
        return text

    digits = lead + rest
    remaining = int(exponent) - (len(digits) - 1)
    width = PSEUDONYM_LENGTH - len(digits) - 1
    if remaining < 0 or len(str(remaining)) > width:
        return text
    return f"{digits}E{remaining:0{width}d}"


class Command(BaseCommand):
    help = "Resolve the pseudonyms in the database back into real names."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rekey",
            action="append",
            required=True,
            metavar="PATH",
            help="A key CSV with 'original' and 'pseudonym' columns. Repeatable.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        names, repaired = self.__load(options["rekey"])
        self.stdout.write(f"Loaded {len(names)} pseudonyms from {len(options['rekey'])} file(s).")
        if repaired:
            self.stdout.write(
                self.style.WARNING(
                    f"  {repaired} pseudonym(s) had been mangled into scientific notation "
                    f"by a spreadsheet and were repaired. Do not open a key in Excel."
                )
            )

        unmatched: dict[str, int] = {}
        counts = {"patients": 0, "families": 0, "fields": 0}

        with transaction.atomic():
            for patient in Patient.objects.select_related("family"):
                changed = False
                for field in ("name", "mother_name"):
                    original = self.__lookup(names, getattr(patient, field), unmatched)
                    if original:
                        setattr(patient, field, original)
                        counts["fields"] += 1
                        changed = True
                if changed:
                    counts["patients"] += 1
                    patient.save()

            for family in Family.objects.all():
                original = self.__lookup(names, family.responsible_name, unmatched)
                if original:
                    family.responsible_name = original
                    counts["families"] += 1
                    counts["fields"] += 1
                    family.save()

            if options["dry_run"]:
                transaction.set_rollback(True)

        self.__report(counts, unmatched, options["dry_run"])

    @staticmethod
    def __lookup(names, value, unmatched):
        """The real name behind a value, recording it when there is none."""
        text = (value or "").strip()
        if not text:
            return None
        original = names.get(text.upper())
        if original is None:
            unmatched[text] = unmatched.get(text, 0) + 1
        return original

    def __load(self, paths):
        """``{pseudonym: original}`` across every key file given."""
        names: dict[str, str] = {}
        repaired = 0

        for path in paths:
            try:
                with open(path, newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    columns = {(name or "").strip().lower(): name for name in reader.fieldnames or []}
                    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
                    if missing:
                        raise CommandError(
                            f"{path} has no {' or '.join(missing)} column; its header is "
                            f"{reader.fieldnames}"
                        )

                    for row in reader:
                        original = (row[columns["original"]] or "").strip()
                        pseudonym = (row[columns["pseudonym"]] or "").strip()
                        if not (original and pseudonym):
                            continue
                        restored = unmangle(pseudonym)
                        repaired += restored != pseudonym
                        key = restored.upper()
                        if names.get(key, original) != original:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  {key} maps to both {names[key]!r} and {original!r}; "
                                    f"keeping the first"
                                )
                            )
                            continue
                        names[key] = original
            except OSError as exc:
                raise CommandError(str(exc)) from exc

        return names, repaired

    def __report(self, counts, unmatched, dry_run):
        if unmatched:
            self.stdout.write(self.style.MIGRATE_HEADING("\nNo key entry for"))
            for text, times in sorted(unmatched.items(), key=lambda item: -item[1])[:10]:
                self.stdout.write(f"  {text}  ×{times}")
            if len(unmatched) > 10:
                self.stdout.write(f"  ... and {len(unmatched) - 10} more")

        verb = "Would restore" if dry_run else "Restored"
        self.stdout.write(
            f"\n{verb} {counts['fields']} names across {counts['patients']} patients "
            f"and {counts['families']} families. {len(unmatched)} values had no key entry."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: the transaction was rolled back."))

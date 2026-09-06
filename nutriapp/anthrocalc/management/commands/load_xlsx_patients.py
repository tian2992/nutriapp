"""Load children and their measurement rounds from a field workbook.

    ./manage.py load_xlsx_patients --file scripts/tabulacion.xlsx --dry-run
    ./manage.py load_xlsx_patients --file scripts/tabulacion.xlsx

Which columns hold what comes from a profile, so a differently shaped file is
``--profile mylayout.json`` rather than a code change. Draft one for a new file
with ``./manage.py inspect_xlsx_layout``. The sheet layout and the reasoning
behind every rule live in ``anthrocalc/bulk_import.py`` and
``docs/features/bulk_patients/``.
"""

import datetime as dt

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from anthrocalc import bulk_import
from anthrocalc.models import Community, Family, Metric, MultipleVisit, Patient, Visit

# Visits are stored at local midday. Stored as midnight they would cross into
# the previous day once Django converted them to UTC, and the z-score code
# derives age from ``visit.date.date()``.
VISIT_HOUR = 12


class _DryRun(Exception):
    """Unwinds the transaction once a dry run has done all its work."""


class Command(BaseCommand):
    help = "Load patients, visits and metrics from a NIMACABAJ field workbook."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to the .xlsx workbook.")
        parser.add_argument(
            "--profile",
            default=bulk_import.DEFAULT_PROFILE.name,
            help=(
                "Layout to read the sheet with: a built-in name "
                f"({', '.join(sorted(bulk_import.PROFILES))}) or a path to a profile JSON."
            ),
        )
        parser.add_argument(
            "--sheet",
            default=None,
            help="Worksheet to read. Defaults to the one the profile names.",
        )
        parser.add_argument(
            "--batch-id",
            default=None,
            help="Label recorded on the jornadas this run touches. Defaults to today's date.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do all the work, report it, then roll back.",
        )
        parser.add_argument(
            "--quiet-warnings",
            action="store_true",
            help="Print only the warning counts, not each warning.",
        )

    def handle(self, *args, **options):
        path = options["file"]
        batch_id = options["batch_id"] or f"bulk_{timezone.localdate():%Y-%m-%d}"
        dry_run = options["dry_run"]

        try:
            profile = bulk_import.load_profile(options["profile"])
            sheet_name = options["sheet"] or profile.sheet_name
            parsed = bulk_import.parse_workbook(path, profile, sheet_name)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f"{path} · sheet {sheet_name!r} · profile {profile.name!r} "
            f"({len(profile.blocks)} rounds) · batch {batch_id}"
            + (" · DRY RUN (nothing will be kept)" if dry_run else "")
        )
        self.stdout.write(
            f"Parsed {len(parsed.patients)} children and {parsed.occasion_count} measurement rounds.\n"
        )

        self.__counts = {
            "patients_created": 0,
            "patients_matched": 0,
            "visits_created": 0,
            "visits_existing": 0,
            "metrics_written": 0,
            "zscores_missing": 0,
        }

        try:
            with transaction.atomic():
                for record in parsed.patients:
                    self.__load_patient(record, batch_id)
                if dry_run:
                    raise _DryRun
        except _DryRun:
            pass

        self.__report(parsed, dry_run, options["quiet_warnings"])

    def __load_patient(self, record, batch_id):
        community, _ = Community.objects.get_or_create(name=record.community)
        family, _ = Family.objects.get_or_create(
            responsible_name=record.mother_name, community=community
        )

        # Codes are duplicated across unrelated children in the source, so the
        # name and date of birth together are what identify a child.
        patient, created = Patient.objects.get_or_create(
            name=record.name,
            dob=record.dob,
            defaults={"code": record.code, "gender": record.gender, "family": family},
        )
        if created:
            self.__counts["patients_created"] += 1
        else:
            self.__counts["patients_matched"] += 1
            patient.code = record.code
            patient.gender = record.gender
            patient.family = family

        patient.mother_name = record.mother_name
        patient.save()

        for occasion in record.occasions:
            self.__load_occasion(patient, community, occasion, batch_id)

    def __load_occasion(self, patient, community, occasion, batch_id):
        moment = timezone.make_aware(
            dt.datetime.combine(occasion.date, dt.time(hour=VISIT_HOUR))
        )
        jornada, _ = MultipleVisit.objects.get_or_create(
            community=community,
            date=moment,
            defaults={"notes": f"Importada de hoja de campo · {batch_id}"},
        )

        visit, created = Visit.objects.get_or_create(
            patient=patient,
            date=moment,
            defaults={"multiple_visit": jornada, "notes": occasion.notes},
        )
        if created:
            self.__counts["visits_created"] += 1
        else:
            self.__counts["visits_existing"] += 1
            visit.multiple_visit = jornada
            if occasion.notes:
                visit.notes = occasion.notes
            visit.save()

        metric, _ = Metric.objects.update_or_create(
            visit=visit,
            defaults={"weight": occasion.weight, "height": occasion.height},
        )
        self.__counts["metrics_written"] += 1
        if metric.wfhz is None:
            self.__counts["zscores_missing"] += 1

    def __report(self, parsed, dry_run, quiet_warnings):
        self.stdout.write(self.style.MIGRATE_HEADING("Children"))
        for record in parsed.patients:
            span = ""
            if record.occasions:
                first, last = record.occasions[0].date, record.occasions[-1].date
                span = f"  {first} → {last}"
            flags = []
            if record.code_was_generated:
                flags.append("code generated")
            if record.gender == bulk_import.GENDER_UNKNOWN:
                flags.append("sex unknown")
            suffix = f"  [{', '.join(flags)}]" if flags else ""
            self.stdout.write(
                f"  row {record.row:>3}  {record.code:<12} {record.name:<14} "
                f"{record.gender} {record.dob}  {len(record.occasions):>2} rounds{span}{suffix}"
            )

        if parsed.skipped:
            self.stdout.write(self.style.MIGRATE_HEADING("\nRows skipped"))
            for skipped in parsed.skipped:
                self.stdout.write(
                    self.style.WARNING(f"  row {skipped.row:>3}  {skipped.name}: {skipped.reason}")
                )

        warnings = [(r, w) for r in parsed.patients for w in r.warnings]
        warnings += [
            (r, f"round {o.block} ({o.date}): {w}")
            for r in parsed.patients
            for o in r.occasions
            for w in o.warnings
        ]
        approximate = [
            (r, o) for r in parsed.patients for o in r.occasions if o.date_is_approximate
        ]

        if warnings and not quiet_warnings:
            self.stdout.write(self.style.MIGRATE_HEADING("\nWarnings"))
            for record, message in warnings:
                self.stdout.write(f"  row {record.row:>3}  {record.name}: {message}")

        counts = self.__counts
        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.MIGRATE_HEADING("\nSummary"))
        self.stdout.write(
            f"  {verb} {counts['patients_created']} patients, matched {counts['patients_matched']} existing.\n"
            f"  {verb} {counts['visits_created']} visits, reused {counts['visits_existing']} existing.\n"
            f"  {counts['metrics_written']} metrics written, "
            f"{counts['zscores_missing']} of them without a weight-for-height z-score.\n"
            f"  {len(approximate)} visits carry an approximate date.\n"
            f"  {len(warnings)} warnings, {len(parsed.skipped)} rows skipped."
        )
        if dry_run:
            self.stdout.write(self.style.WARNING("\n  Dry run: the transaction was rolled back."))

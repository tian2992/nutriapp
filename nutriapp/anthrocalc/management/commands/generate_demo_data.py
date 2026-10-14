import datetime
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from anthrocalc.models import (
    Community,
    EnvironmentMetric,
    Family,
    HouseholdStatus,
    Metric,
    Patient,
    Visit,
    WaterSource,
)

# Ages a jornada-style campaign realistically hits; each patient gets a random
# subset of these, not all of them, to mimic irregular attendance.
VISIT_AGE_SCHEDULE_MONTHS = [1, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39]


class Command(BaseCommand):
    help = (
        "Generate synthetic patients/families/visits with realistic, irregular "
        "jornada-style visit ages, for exercising export_longform, "
        "growth_model_coverage_report, and analysis/growth_splines.R without "
        "real patient data. Refuses to run against a database that already "
        "has Patient rows unless --force is passed - this is meant for empty "
        "dev/test databases, never for one that might hold real clinic records."
    )

    def add_arguments(self, parser):
        parser.add_argument("--patients", type=int, default=12, help="Number of synthetic patients (default: 12).")
        parser.add_argument("--min-visits", type=int, default=8, help="Minimum visits per patient (default: 8).")
        parser.add_argument("--max-visits", type=int, default=14, help="Maximum visits per patient (default: 14).")
        parser.add_argument(
            "--community", default="Aldea Demo", help="Name of the community to create (default: 'Aldea Demo')."
        )
        parser.add_argument("--seed", type=int, default=42, help="Random seed, for reproducible runs (default: 42).")
        parser.add_argument(
            "--no-household-history",
            action="store_true",
            help="Skip creating historical HouseholdStatus snapshots.",
        )
        parser.add_argument(
            "--no-environment",
            action="store_true",
            help="Skip creating EnvironmentMetric rows on visits.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate data generation without saving any changes to the database.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running even if the database already has Patient rows.",
        )

    def handle(self, *args, **options):
        has_existing_records = Patient.objects.exists() or Visit.objects.exists()
        if has_existing_records and not options["force"]:
            raise CommandError(
                "Database already has Patient/Visit rows. This command is for empty dev/test "
                "databases only - re-run with --force if you really want to add fake "
                "patients on top of what's there. Never run this against a database "
                "that might hold real clinic records."
            )

        n_patients = options["patients"]
        if n_patients < 1:
            raise CommandError("--patients must be at least 1.")

        min_visits = options["min_visits"]
        max_visits = options["max_visits"]
        if min_visits > max_visits:
            raise CommandError("--min-visits cannot be greater than --max-visits.")
        if min_visits < 1:
            raise CommandError("--min-visits must be at least 1.")

        rng = random.Random(options["seed"])
        include_household_history = not options["no_household_history"]
        include_environment = not options["no_environment"]
        dry_run = options["dry_run"]

        with transaction.atomic():
            community, _ = Community.objects.get_or_create(name=options["community"])
            well = river = None
            if include_household_history:
                well, _ = WaterSource.objects.get_or_create(name="Pozo")
                river, _ = WaterSource.objects.get_or_create(name="Río")

            n_visits_created = 0
            for pi in range(n_patients):
                family = Family.objects.create(responsible_name=f"Familia Demo {pi}", community=community)

                if include_household_history:
                    # Two snapshots out of chronological insertion order, so
                    # Family.status_as_of() has a real before/after to pick between.
                    HouseholdStatus.objects.create(
                        family=family, recorded_at=datetime.date(2024, 6, 1), water_source=river
                    )
                    HouseholdStatus.objects.create(
                        family=family, recorded_at=datetime.date(2023, 1, 1), water_source=well
                    )

                dob = datetime.date(2021, 1, 1) + datetime.timedelta(days=rng.randint(0, 700))
                gender = "M" if pi % 2 == 0 else "F"
                birth_height = rng.uniform(48.0, 52.0)
                growth_rate = rng.uniform(0.55, 0.75)
                birth_weight = rng.uniform(2.9, 3.6)

                base_code = f"DEMO{pi}"
                code = base_code
                suffix = 1
                while Patient.objects.filter(code=code).exists():
                    code = f"{base_code}_{suffix}"
                    suffix += 1

                patient = Patient.objects.create(
                    code=code,
                    name=f"Niño Demo {pi}",
                    gender=gender,
                    dob=dob,
                    family=family,
                    enrolled_on=dob,
                )

                n_visits = rng.randint(min_visits, max_visits)
                n_visits = min(n_visits, len(VISIT_AGE_SCHEDULE_MONTHS))
                visit_ages = sorted(rng.sample(VISIT_AGE_SCHEDULE_MONTHS, n_visits))

                for age_m in visit_ages:
                    visit_date = dob + datetime.timedelta(days=int(age_m * 30.4375))
                    height = birth_height + growth_rate * (age_m**0.7) * 6 + rng.gauss(0, 0.8)
                    weight = birth_weight + (age_m**0.72) * 0.75 + rng.gauss(0, 0.2)
                    standing = age_m >= 24

                    visit_datetime = timezone.make_aware(
                        datetime.datetime.combine(visit_date, datetime.time(9, 0))
                    )
                    visit = Visit.objects.create(patient=patient, date=visit_datetime)
                    Metric.objects.create(
                        visit=visit,
                        weight=round(weight, 2),
                        height=round(height, 1),
                        standing_or_upright=standing,
                    )
                    if include_environment:
                        EnvironmentMetric.objects.create(
                            visit=visit,
                            dietary_diversity_score=rng.randint(2, 8),
                            breastfeeding=age_m < 24,
                        )
                    n_visits_created += 1

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"[DRY-RUN] Simulated creation of {n_patients} patients and {n_visits_created} visits in community "
                        f"'{community.name}' (seed={options['seed']}). Database was not modified."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {n_patients} patients and {n_visits_created} visits in community "
                        f"'{community.name}' (seed={options['seed']})."
                    )
                )

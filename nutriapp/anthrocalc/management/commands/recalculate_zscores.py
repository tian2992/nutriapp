"""Recompute WAZ/HAZ/WHZ for existing Metric rows.

Useful after WHZ table-selection fixes, to fill stale wfhz=None values that
fall inside the WHO WFL/WFH ranges (45–120 cm).

    ./manage.py recalculate_zscores --dry-run
    ./manage.py recalculate_zscores --only-missing-whz
    ./manage.py recalculate_zscores
"""

from django.core.management.base import BaseCommand

from anthrocalc.models import Metric


class Command(BaseCommand):
    help = "Recompute z-scores on Metric rows (optionally only missing WHZ)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-missing-whz",
            action="store_true",
            help="Only rows with weight+height set and wfhz NULL.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count candidates without saving.",
        )

    def handle(self, *args, **options):
        qs = Metric.objects.filter(weight__isnull=False, height__isnull=False)
        if options["only_missing_whz"]:
            qs = qs.filter(wfhz__isnull=True)

        qs = qs.select_related("visit__patient").order_by("pk")
        total = qs.count()
        self.stdout.write(f"Candidates: {total}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes saved."))
            return

        updated = 0
        still_missing_whz = 0
        for metric in qs.iterator(chunk_size=200):
            before = metric.wfhz
            # Metric.save() recalculates z-scores.
            metric.save()
            metric.refresh_from_db(fields=["wfaz", "hfaz", "wfhz"])
            if metric.wfhz != before or metric.wfhz is not None:
                updated += 1
            if metric.wfhz is None:
                still_missing_whz += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Saved {total} metrics ({still_missing_whz} still missing WHZ)."
            )
        )

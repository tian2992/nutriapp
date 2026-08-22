import pathlib

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from anthrocalc.analytics import build_longform_dataframe


class Command(BaseCommand):
    help = (
        "Export the one-row-per-visit long-form dataset (growth measurements, "
        "environment observations, and household status as of each visit) for "
        "statistical modeling in R, Python, or any other tool that can read a "
        "flat file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["csv", "parquet"],
            default="parquet",
            help="Output file format (default: parquet).",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Output file path. Defaults to exports/longform_<timestamp>.<ext>.",
        )

    def handle(self, *args, **options):
        df = build_longform_dataframe()

        fmt = options["format"]
        output = options["output"]
        if not output:
            exports_dir = pathlib.Path(settings.BASE_DIR) / "exports"
            exports_dir.mkdir(exist_ok=True)
            timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
            output = exports_dir / f"longform_{timestamp}.{fmt}"
        output = pathlib.Path(output)

        if fmt == "csv":
            df.to_csv(output, index=False)
        else:
            df.to_parquet(output, index=False)

        self.stdout.write(self.style.SUCCESS(f"Wrote {len(df)} visit rows ({len(df.columns)} columns) to {output}"))

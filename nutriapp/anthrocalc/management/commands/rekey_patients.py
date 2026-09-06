import csv

from django.core.management.base import BaseCommand

from anthrocalc.models import Family, Patient


class Command(BaseCommand):
    help = "Resolve rekey.csv hashes back into names against the DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rekey",
            required=True,
            help="Path to a rekey.csv mapping pseudonym -> original name.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        rekey = self.__load_rekey(options["rekey"])
        self.stdout.write(f"Loaded {len(rekey)} entries.")

        matched = missing = updated = 0

        for patient in Patient.objects.all():
            changed = False

            # Column 8 -> Patient.name (kid)
            kid = patient.name
            if kid is not None and kid.strip():
                original = rekey.get(kid.strip().upper())
                if original:
                    patient.name = original
                    changed = True
                    matched += 1
                else:
                    missing += 1

            # Column 10 -> Family.responsible_name (guardian)
            guardian = patient.family.responsible_name if patient.family else None
            if guardian and guardian.strip():
                original = rekey.get(guardian.strip().upper())
                if original:
                    patient.family.responsible_name = original
                    changed = True
                    matched += 1
                else:
                    missing += 1

            if changed:
                updated += 1
                if not options["dry_run"]:
                    patient.save()
                    if patient.family:
                        patient.family.save()

        verb = "Would update" if options["dry_run"] else "Updated"
        self.stdout.write(
            f"{verb} {updated} patients · "
            f"{matched} names matched · {missing} unmatched."
        )

    @staticmethod
    def __load_rekey(path):
        """Return {pseudonym_upper: original_name}.

        Headers are skipped. The key is stored upper so the lookup mirrors the
        normalizer used when pseudonyms were generated.
        """
        keymap = {}
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) != 4:
                    continue
                # (column, entity, original, pseudonym)
                pseudonym, original = row[3], row[2]
                if pseudonym and original:
                    keymap[pseudonym.strip().upper()] = original.strip()
        return keymap

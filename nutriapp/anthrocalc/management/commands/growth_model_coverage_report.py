from django.core.management.base import BaseCommand

from anthrocalc.analytics import build_longform_dataframe


class Command(BaseCommand):
    help = (
        "Report whether the current data can support a subject-specific growth-curve "
        "mixed model (random slopes, cubic splines, CAR(1) residuals) in the style of "
        "Grajeda et al. 2016 - or whether the model needs to be simplified first. Run "
        "this before writing/fitting an R script, not after it fails to converge."
    )

    def handle(self, *args, **options):
        df = build_longform_dataframe()
        out = self.stdout

        if df.empty:
            out.write(self.style.WARNING("No visits found - nothing to report."))
            return

        out.write(self.style.MIGRATE_HEADING("Observations per child"))
        per_patient = df.groupby("patient_id").size()
        out.write(f"  patients: {per_patient.shape[0]}")
        out.write(f"  visits:   {len(df)}")
        out.write(
            "  per-patient visit count - min/25%/median/75%/max: "
            f"{per_patient.min()}/{int(per_patient.quantile(.25))}/{int(per_patient.median())}/"
            f"{int(per_patient.quantile(.75))}/{per_patient.max()}"
        )
        thin = (per_patient < 4).sum()
        out.write(f"  patients with < 4 visits (can't support random slope + spline): {thin}")

        out.write(self.style.MIGRATE_HEADING("Age coverage"))
        age_first = df.groupby("patient_id")["age_months"].min()
        age_last = df.groupby("patient_id")["age_months"].max()
        out.write(f"  age at first visit (months) - min/median/max: {age_first.min():.1f}/{age_first.median():.1f}/{age_first.max():.1f}")
        out.write(f"  age at last visit  (months) - min/median/max: {age_last.min():.1f}/{age_last.median():.1f}/{age_last.max():.1f}")
        out.write(
            "  overall age_months distribution - 5%/25%/50%/75%/95%: "
            + "/".join(f"{df['age_months'].quantile(q):.1f}" for q in (0.05, 0.25, 0.5, 0.75, 0.95))
        )
        started_near_birth = (age_first <= 3).sum()
        out.write(
            f"  patients first measured at <=3 months (matches paper's knot at 3): {started_near_birth} "
            f"of {age_first.shape[0]}"
        )

        out.write(self.style.MIGRATE_HEADING("Duplicate timepoints (corCAR1 hard-errors on these)"))
        dupes = df.groupby(["patient_id", "visit_date"]).size()
        dupes = dupes[dupes > 1]
        out.write(f"  (patient_id, visit_date) pairs with >1 visit: {dupes.shape[0]}")
        if not dupes.empty:
            out.write("  affected patient_ids: " + ", ".join(str(p) for p in sorted(set(i[0] for i in dupes.index))[:20]))

        out.write(self.style.MIGRATE_HEADING("Field completeness"))
        out.write(f"  height null rate: {df['height'].isna().mean():.1%}")
        out.write(f"  standing_or_upright null rate: {df['standing_or_upright'].isna().mean():.1%}")
        crosstab_note = "n/a (need both fields populated)"
        known = df.dropna(subset=["standing_or_upright", "age_months"])
        if not known.empty:
            # Paper's proxy: standing/height measurement assumed once age > 24 months.
            agree = ((known["age_months"] > 24) == known["standing_or_upright"]).mean()
            crosstab_note = f"{agree:.1%} of rows agree with the paper's I(age>24) proxy"
        out.write(f"  standing_or_upright vs age>24 proxy: {crosstab_note}")

        out.write(self.style.MIGRATE_HEADING("Sex coding (Patient.gender)"))
        out.write(f"  value counts: {dict(df['gender'].value_counts(dropna=False))}")

        out.write(self.style.MIGRATE_HEADING("Family nesting"))
        per_family = df.groupby("family_id")["patient_id"].nunique()
        multi_child_families = (per_family > 1).sum()
        out.write(
            f"  families with >1 child in the data: {multi_child_families} of {per_family.shape[0]} "
            "(0 or near-0 means family-level nesting isn't structurally present, same as the paper's cohort)"
        )

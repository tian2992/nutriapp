import datetime
from io import StringIO

from django.core.management import call_command, CommandError
from django.test import TestCase
from django.utils import timezone

from anthrocalc.analytics import build_longform_dataframe
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


class GenerateDemoDataCommandTests(TestCase):
    def test_generates_demo_data_on_empty_database(self):
        out = StringIO()
        call_command("generate_demo_data", patients=3, min_visits=2, max_visits=4, seed=123, stdout=out)
        output = out.getvalue()

        self.assertIn("Created 3 patients", output)
        self.assertIn("Aldea Demo", output)
        self.assertEqual(Patient.objects.count(), 3)
        self.assertTrue(Visit.objects.count() >= 6)
        self.assertEqual(Community.objects.filter(name="Aldea Demo").count(), 1)
        self.assertEqual(Family.objects.count(), 3)
        self.assertTrue(HouseholdStatus.objects.count() > 0)
        self.assertTrue(EnvironmentMetric.objects.count() > 0)

        for p in Patient.objects.all():
            self.assertTrue(p.code.startswith("DEMO"))
            self.assertIn(p.gender, ["M", "F"])
            self.assertIsNotNone(p.dob)
            self.assertIsNotNone(p.enrolled_on)
            visits = Visit.objects.filter(patient=p)
            self.assertTrue(visits.exists())
            for v in visits:
                self.assertIsNotNone(v.date.tzinfo)
                self.assertTrue(hasattr(v, "metric"))
                self.assertIsNotNone(v.metric.weight)
                self.assertIsNotNone(v.metric.height)

    def test_refuses_to_run_when_patients_exist_without_force(self):
        community = Community.objects.create(name="Existing Comm")
        family = Family.objects.create(responsible_name="Fam 1", community=community)
        Patient.objects.create(
            name="Existing Child",
            code="EX01",
            gender="M",
            dob=datetime.date(2022, 1, 1),
            family=family,
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("generate_demo_data", stdout=StringIO())

        self.assertIn("Database already has Patient/Visit rows", str(ctx.exception))
        self.assertIn("--force", str(ctx.exception))

    def test_refuses_to_run_when_visits_exist_without_force(self):
        community = Community.objects.create(name="Existing Comm")
        family = Family.objects.create(responsible_name="Fam 1", community=community)
        patient = Patient.objects.create(
            name="Existing Child",
            code="EX01",
            gender="M",
            dob=datetime.date(2022, 1, 1),
            family=family,
        )
        Visit.objects.create(patient=patient, date=timezone.now())

        # Delete patient to test visit-only check
        # But cascading deletes visit in Django, so let's check with patient and visit
        with self.assertRaises(CommandError) as ctx:
            call_command("generate_demo_data", stdout=StringIO())

        self.assertIn("Database already has Patient/Visit rows", str(ctx.exception))

    def test_runs_with_force_when_data_exists(self):
        community = Community.objects.create(name="Existing Comm")
        family = Family.objects.create(responsible_name="Fam 1", community=community)
        Patient.objects.create(
            name="Existing Child",
            code="DEMO0",
            gender="M",
            dob=datetime.date(2022, 1, 1),
            family=family,
        )

        out = StringIO()
        call_command("generate_demo_data", patients=2, min_visits=2, max_visits=3, force=True, stdout=out)
        self.assertIn("Created 2 patients", out.getvalue())
        # DEMO0 already existed, so new patients get unique codes
        self.assertEqual(Patient.objects.count(), 3)
        codes = list(Patient.objects.values_list("code", flat=True))
        self.assertEqual(len(codes), len(set(codes)))

    def test_dry_run_leaves_database_unmodified(self):
        out = StringIO()
        call_command("generate_demo_data", patients=5, min_visits=3, max_visits=5, dry_run=True, stdout=out)
        output = out.getvalue()

        self.assertIn("[DRY-RUN] Simulated creation of 5 patients", output)
        self.assertIn("Database was not modified", output)
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Visit.objects.count(), 0)
        self.assertEqual(Community.objects.count(), 0)
        self.assertEqual(Family.objects.count(), 0)

    def test_input_validations(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("generate_demo_data", patients=0, stdout=StringIO())
        self.assertIn("--patients must be at least 1", str(ctx.exception))

        with self.assertRaises(CommandError) as ctx:
            call_command("generate_demo_data", min_visits=0, stdout=StringIO())
        self.assertIn("--min-visits must be at least 1", str(ctx.exception))

        with self.assertRaises(CommandError) as ctx:
            call_command("generate_demo_data", min_visits=10, max_visits=5, stdout=StringIO())
        self.assertIn("--min-visits cannot be greater than --max-visits", str(ctx.exception))

    def test_flags_disable_household_and_environment(self):
        out = StringIO()
        call_command(
            "generate_demo_data",
            patients=2,
            min_visits=2,
            max_visits=3,
            no_household_history=True,
            no_environment=True,
            stdout=out,
        )
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(HouseholdStatus.objects.count(), 0)
        self.assertEqual(EnvironmentMetric.objects.count(), 0)

    def test_downstream_analytics_and_coverage_report(self):
        out = StringIO()
        call_command("generate_demo_data", patients=5, min_visits=4, max_visits=8, seed=99, stdout=out)

        df = build_longform_dataframe()
        self.assertFalse(df.empty)
        self.assertEqual(df["patient_id"].nunique(), 5)
        self.assertTrue((df["weight"] > 0).all())
        self.assertTrue((df["height"] > 0).all())

        report_out = StringIO()
        call_command("growth_model_coverage_report", stdout=report_out)
        report_text = report_out.getvalue()
        self.assertIn("Observations per child", report_text)
        self.assertIn("Age coverage", report_text)
        self.assertIn("Field completeness", report_text)

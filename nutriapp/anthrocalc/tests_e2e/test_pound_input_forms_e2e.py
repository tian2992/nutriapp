import datetime

from anthrocalc.models import Community, Family, Metric, Patient, Visit

from .base import PlaywrightTestCase


class PoundInputFormsE2ETests(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.login_as_field_agent()
        self.community = Community.objects.create(name="Comunidad Libras E2E")
        self.family = Family.objects.create(responsible_name="Familia Libras", community=self.community)
        self.patient1 = Patient.objects.create(
            code="LIB-01",
            name="Ana Libras",
            gender="F",
            dob=datetime.date(2022, 1, 15),
            family=self.family,
        )
        self.patient2 = Patient.objects.create(
            code="LIB-02",
            name="Carlos Libras",
            gender="M",
            dob=datetime.date(2021, 6, 1),
            family=self.family,
        )

    def test_individual_metric_form_kg_default_and_lb_conversion(self):
        # 1. Standard kg entry
        visit1 = Visit.objects.create(patient=self.patient1, date=datetime.datetime(2026, 8, 1, 10, 0, tzinfo=datetime.timezone.utc))
        self.page.goto(f"{self.live_server_url}/metric/new?visit={visit1.id}")
        self.page.wait_for_load_state("networkidle")

        self.page.fill("#id_weight", "12.50")
        self.page.fill("#id_height", "85.0")
        self.page.click("input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        metric1 = Metric.objects.get(visit=visit1)
        self.assertEqual(metric1.weight, 12.50)
        self.assertEqual(metric1.height, 85.0)

        # 2. Pound entry: 22.04 lb -> 10.00 kg
        visit2 = Visit.objects.create(patient=self.patient1, date=datetime.datetime(2026, 9, 1, 10, 0, tzinfo=datetime.timezone.utc))
        self.page.goto(f"{self.live_server_url}/metric/new?visit={visit2.id}")
        self.page.wait_for_load_state("networkidle")

        # Click "lb" toggle
        lb_button = self.page.locator(".weight-unit-toggle button[data-unit='lb'], button[data-unit='lb']").first
        lb_button.click()

        self.page.fill("#id_weight", "22.04")
        self.page.fill("#id_height", "75.0")
        self.page.select_option("#id_standing_or_upright", label="No")

        # Check real-time feedback badge
        feedback = self.page.locator(".weight-conversion-feedback").first.text_content()
        self.assertIn("10.00 kg", feedback)

        self.page.click("input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        metric2 = Metric.objects.get(visit=visit2)
        self.assertEqual(metric2.weight, 10.00)
        self.assertEqual(metric2.height, 75.0)
        # Verify calculated WHO Z-scores exist and are computed based on 10.00 kg
        self.assertIsNotNone(metric2.wfaz)
        self.assertIsNotNone(metric2.wfhz)

    def test_mass_visit_master_toggle_and_row_level_conversion(self):
        self.page.goto(f"{self.live_server_url}/communities/{self.community.id}/mass-visit/")
        self.page.wait_for_load_state("networkidle")
        self.page.fill("#id_date", "2026-10-15")

        # Click master toggle in table header to switch to pounds
        master_lb_btn = self.page.locator("#mass-unit-toggle button[data-unit='lb']")
        master_lb_btn.click()

        # Child A: Ana Libras (row 0) -> 15.5 lb -> 7.03 kg
        self.page.fill("#id_rows-0-weight", "15.5")
        self.page.fill("#id_rows-0-height", "68.0")
        self.page.select_option("#id_rows-0-standing_or_upright", "False")

        # Child B: Carlos Libras (row 1) -> 25.0 lb -> 11.34 kg
        self.page.fill("#id_rows-1-weight", "25.0")
        self.page.fill("#id_rows-1-height", "82.0")
        self.page.select_option("#id_rows-1-standing_or_upright", "True")

        # Verify live row feedbacks
        row0_feedback = self.page.locator("#patient-row-" + str(self.patient1.id) + " .weight-row-feedback").text_content()
        self.assertIn("7.03 kg", row0_feedback)

        row1_feedback = self.page.locator("#patient-row-" + str(self.patient2.id) + " .weight-row-feedback").text_content()
        self.assertIn("11.34 kg", row1_feedback)

        # Batch submit
        self.page.locator("#massVisitForm button.btn-success").click()
        self.page.wait_for_load_state("networkidle")

        visit_ana = Visit.objects.get(patient=self.patient1)
        metric_ana = Metric.objects.get(visit=visit_ana)
        self.assertEqual(metric_ana.weight, 7.03)
        self.assertEqual(metric_ana.height, 68.0)

        visit_carlos = Visit.objects.get(patient=self.patient2)
        metric_carlos = Metric.objects.get(visit=visit_carlos)
        self.assertEqual(metric_carlos.weight, 11.34)
        self.assertEqual(metric_carlos.height, 82.0)

    def test_patient_birth_weight_pound_input(self):
        self.page.goto(f"{self.live_server_url}/patient/new")
        self.page.wait_for_load_state("networkidle")

        self.page.fill("#id_name", "Bebe Nuevo Libras")
        self.page.select_option("#id_gender", "M")
        self.page.fill("#id_dob", "2026-01-10")
        self.page.fill("#id_new_community_name", "Comunidad Bebe")
        self.page.fill("#id_new_family_name", "Familia Bebe")

        # Switch birth weight toggle to lb
        birth_weight_input = self.page.locator("#id_birth_weight")
        birth_weight_container = birth_weight_input.locator("..")
        lb_btn = birth_weight_container.locator("button[data-unit='lb']")
        lb_btn.click()

        self.page.fill("#id_birth_weight", "7.5")
        self.page.fill("#id_birth_length", "49.5")

        self.page.click("form button[type=submit], form input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        patient = Patient.objects.get(name="Bebe Nuevo Libras")
        self.assertEqual(patient.birth_weight, 3.40)
        self.assertEqual(patient.birth_length, 49.5)

    def test_bidirectional_toggle_switching(self):
        visit = Visit.objects.create(patient=self.patient1, date=datetime.datetime(2026, 10, 1, 10, 0, tzinfo=datetime.timezone.utc))
        self.page.goto(f"{self.live_server_url}/metric/new?visit={visit.id}")
        self.page.wait_for_load_state("networkidle")

        # Enter 10.00 kg
        self.page.fill("#id_weight", "10.00")

        # Click lb toggle -> converts to 22.05 lb
        lb_btn = self.page.locator(".weight-unit-toggle button[data-unit='lb']").first
        lb_btn.click()
        val_in_lb = self.page.input_value("#id_weight")
        self.assertEqual(val_in_lb, "22.05")

        # Click kg toggle -> converts back to 10.00 kg
        kg_btn = self.page.locator(".weight-unit-toggle button[data-unit='kg']").first
        kg_btn.click()
        val_in_kg = self.page.input_value("#id_weight")
        self.assertEqual(val_in_kg, "10.00")

    def test_validation_failure_re_render_preserves_unit_and_conversion(self):
        visit = Visit.objects.create(patient=self.patient1, date=datetime.datetime(2026, 10, 5, 10, 0, tzinfo=datetime.timezone.utc))
        self.page.goto(f"{self.live_server_url}/metric/new?visit={visit.id}")
        self.page.wait_for_load_state("networkidle")

        # Switch to lb
        lb_btn = self.page.locator(".weight-unit-toggle button[data-unit='lb']").first
        lb_btn.click()

        # Enter weight in lb, leave height empty so validation fails
        self.page.fill("#id_weight", "22.04")
        self.page.click("input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        # Re-rendered / retained page: weight preserved in lb mode without corruption
        val = self.page.input_value("#id_weight")
        self.assertEqual(val, "22.04")  # preserved exact value entered in lb

        # Now fill height and submit
        self.page.fill("#id_height", "78.0")
        self.page.click("input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        metric = Metric.objects.get(visit=visit)
        self.assertEqual(metric.weight, 10.00)
        self.assertEqual(metric.height, 78.0)

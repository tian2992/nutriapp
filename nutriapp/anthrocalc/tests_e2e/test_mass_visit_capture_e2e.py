"""Baseline E2E regression test for the mass-visit (jornada) capture flow.

This exercises UI that already exists today (CommunityMassVisit /
community_mass_visit.html) - it should PASS against the current code.
Its job is to catch regressions while specs in docs/specs/ change this
same form (guardrails_metricas.md, advertencia_visita_mensual.md), not to
verify anything new. If you land a spec and this test starts failing,
that's either an intentional behavior change (update the test) or a
regression (fix the code).

Contrast with test_patient_registration_e2e.py, which is spec-driven and
expected to fail until buscar_paciente_existente.md ships.
"""

import datetime

from anthrocalc.models import Community, Family, Metric, Patient, Visit

from .base import PlaywrightTestCase


class MassVisitCaptureE2ETests(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.login_as_field_agent()
        self.community = Community.objects.create(name="Comunidad E2E")
        family = Family.objects.create(responsible_name="Familia E2E", community=self.community)
        # Ordered by name (CommunityMassVisit.get_patients_data) - "Ana" before "Beto".
        self.patient_measured = Patient.objects.create(
            code="E2E-01", name="Ana E2E", gender="F", dob=datetime.date(2022, 1, 15), family=family
        )
        self.patient_skipped = Patient.objects.create(
            code="E2E-02", name="Beto E2E", gender="M", dob=datetime.date(2021, 6, 1), family=family
        )

    def test_fills_one_row_leaves_one_blank_and_only_saves_the_filled_one(self):
        self.page.goto(f"{self.live_server_url}/communities/{self.community.id}/mass-visit/")

        # Row 0 = Ana (filled), row 1 = Beto (left blank on purpose). Both
        # rows' hidden rows-N-patient_id are already populated by the
        # server on GET (views.py:651) - nothing to fill for row 1, its
        # formset entry validates fine with weight/height empty (both are
        # required=False on MassMeasurementRowForm) and just gets skipped
        # by CommunityMassVisit.post's `if form.has_data()` check.
        self.page.fill("#id_rows-0-weight", "9.5")
        self.page.fill("#id_rows-0-height", "72.3")
        self.page.select_option("#id_rows-0-standing_or_upright", "False")

        self.page.click("#massVisitForm button[type=submit], #massVisitForm input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(Visit.objects.count(), 1)
        visit = Visit.objects.get()
        self.assertEqual(visit.patient_id, self.patient_measured.id)

        metric = Metric.objects.get(visit=visit)
        self.assertEqual(metric.weight, 9.5)
        self.assertEqual(metric.height, 72.3)

        self.assertFalse(Visit.objects.filter(patient=self.patient_skipped).exists())

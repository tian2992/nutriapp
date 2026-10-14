"""E2E: jornada capture must not lose measurements when adding children or
batch-saving after some rows were already saved individually.
"""

import datetime

from anthrocalc.models import Community, Family, Metric, MultipleVisit, Patient, Visit

from .base import PlaywrightTestCase


class JornadaDataPreservationE2ETests(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.login_as_field_agent()
        self.community = Community.objects.create(
            name="Comunidad Preservacion E2E", municipality="Rabinal"
        )
        self.family = Family.objects.create(
            responsible_name="Familia Preservacion E2E", community=self.community
        )
        # Name order on mass-visit / jornada tables: Ana, Beto, Carla.
        self.ana = Patient.objects.create(
            code="PRE-01",
            name="Ana Preservacion",
            gender="F",
            dob=datetime.date(2022, 1, 15),
            family=self.family,
        )
        self.beto = Patient.objects.create(
            code="PRE-02",
            name="Beto Preservacion",
            gender="M",
            dob=datetime.date(2021, 6, 1),
            family=self.family,
        )
        self.carla = Patient.objects.create(
            code="PRE-03",
            name="Carla Preservacion",
            gender="F",
            dob=datetime.date(2023, 3, 10),
            family=self.family,
        )

    def test_adding_child_to_jornada_keeps_existing_metrics(self):
        jornada = MultipleVisit.objects.create(
            community=self.community,
            date=datetime.datetime(2026, 8, 17, 12, 0, tzinfo=datetime.timezone.utc),
            responsible_name="Promotor E2E",
        )
        ana_visit = Visit.objects.create(
            patient=self.ana, date=jornada.date, multiple_visit=jornada
        )
        Metric.objects.create(
            visit=ana_visit, weight=11.5, height=82.0, standing_or_upright=True
        )

        jornada_url = (
            f"{self.live_server_url}/communities/{self.community.id}/jornada/{jornada.id}/"
        )
        self.page.goto(jornada_url)
        self.page.wait_for_load_state("networkidle")
        self.assertIn(
            "Jornada",
            self.page.content(),
            f"expected jornada detail, got url={self.page.url} body={self.page.content()[:500]!r}",
        )
        self.page.locator('a[href="?add=1"]').click()
        self.page.wait_for_load_state("networkidle")

        self.page.fill("#jornada-add-q", "Carla")
        self.page.locator('form[role="search"] button[type="submit"]').click()
        self.page.wait_for_load_state("networkidle")

        carla_row = self.page.locator(".list-group-item", has_text="Carla Preservacion")
        carla_row.get_by_role("button", name="Incluir").click()
        self.page.wait_for_load_state("networkidle")

        self.assertTrue(
            Visit.objects.filter(multiple_visit=jornada, patient=self.carla).exists(),
            "Carla should be on the jornada after Incluir",
        )
        self.assertEqual(Visit.objects.filter(multiple_visit=jornada).count(), 2)

        ana_visit.refresh_from_db()
        ana_metric = Metric.objects.get(visit=ana_visit)
        self.assertEqual(ana_visit.multiple_visit_id, jornada.id)
        self.assertEqual(ana_metric.weight, 11.5)
        self.assertEqual(ana_metric.height, 82.0)
        self.assertFalse(
            Metric.objects.filter(visit__patient=self.carla, visit__multiple_visit=jornada).exists(),
            "Incluir must not invent a measurement for the new child",
        )
        self.assertIn("Carla Preservacion", self.page.content())
        self.assertIn("Ana Preservacion", self.page.content())

    def test_batch_save_keeps_per_row_saves_and_stores_remaining_rows(self):
        mass_url = f"{self.live_server_url}/communities/{self.community.id}/mass-visit/"
        self.page.goto(mass_url)
        self.page.wait_for_load_state("networkidle")

        # Row order: Ana=0, Beto=1, Carla=2
        self.page.fill("#id_date", "2026-08-17")
        self.page.fill("#id_responsible_name", "Promotor E2E")

        self.page.fill("#id_rows-0-weight", "12.0")
        self.page.fill("#id_rows-0-height", "85.0")
        self.page.select_option("#id_rows-0-standing_or_upright", "True")

        # Save Ana individually; Beto/Carla typed values must survive the re-render.
        self.page.fill("#id_rows-1-weight", "10.5")
        self.page.fill("#id_rows-1-height", "78.0")
        self.page.fill("#id_rows-1-notes", "borrador beto")

        ana_row = self.page.locator("#patient-row-" + str(self.ana.id))
        ana_row.get_by_role("button", name="Guardar").click()
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(MultipleVisit.objects.filter(community=self.community).count(), 1)
        jornada = MultipleVisit.objects.get(community=self.community)
        ana_metric = Metric.objects.get(visit__patient=self.ana, visit__multiple_visit=jornada)
        self.assertEqual(ana_metric.weight, 12.0)
        self.assertEqual(ana_metric.height, 85.0)
        self.assertFalse(Visit.objects.filter(patient=self.beto, multiple_visit=jornada).exists())

        # Draft values for Beto must still be in the form after per-row save.
        self.assertEqual(self.page.input_value("#id_rows-1-weight"), "10.5")
        self.assertEqual(self.page.input_value("#id_rows-1-height"), "78.0")
        self.assertEqual(self.page.input_value("#id_rows-1-notes"), "borrador beto")
        self.assertIn("Guardado", ana_row.inner_text())

        # Finish Carla without per-row save, then batch-save the jornada.
        self.page.fill("#id_rows-2-weight", "9.0")
        self.page.fill("#id_rows-2-height", "70.0")
        self.page.select_option("#id_rows-2-standing_or_upright", "False")

        self.page.locator("#massVisitForm button.btn-success").click()
        self.page.wait_for_load_state("networkidle")

        self.assertEqual(MultipleVisit.objects.filter(community=self.community).count(), 1)
        jornada.refresh_from_db()
        self.assertEqual(Visit.objects.filter(multiple_visit=jornada).count(), 3)

        ana_metric.refresh_from_db()
        self.assertEqual(ana_metric.weight, 12.0)
        self.assertEqual(ana_metric.height, 85.0)

        beto_metric = Metric.objects.get(visit__patient=self.beto, visit__multiple_visit=jornada)
        self.assertEqual(beto_metric.weight, 10.5)
        self.assertEqual(beto_metric.height, 78.0)
        beto_visit = Visit.objects.get(patient=self.beto, multiple_visit=jornada)
        self.assertEqual(beto_visit.notes, "borrador beto")

        carla_metric = Metric.objects.get(visit__patient=self.carla, visit__multiple_visit=jornada)
        self.assertEqual(carla_metric.weight, 9.0)
        self.assertEqual(carla_metric.height, 70.0)

        self.assertTrue(
            self.page.url.rstrip("/").endswith(
                f"/communities/{self.community.id}/jornada/{jornada.id}"
            ),
            f"expected redirect to jornada detail, got {self.page.url}",
        )

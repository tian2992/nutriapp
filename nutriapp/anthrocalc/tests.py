import datetime
import pandas as pd
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .analytics import build_longform_dataframe
from .forms import PatientForm, MassMeasurementRowForm
from .models import Community, EnvironmentMetric, Family, HouseholdStatus, Metric, MultipleVisit, Patient, Visit, WaterSource
from .person_utils import get_nutritional_status

User = get_user_model()


class BaseAuthenticatedTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testpromotor", password="password123")
        self.client = Client()
        self.client.login(username="testpromotor", password="password123")


class ListTemplateTests(BaseAuthenticatedTestCase):
    def test_patient_list_uses_patient_template(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/patient_list.html", [template.name for template in response.templates])

    def test_metric_list_uses_metric_template(self):
        response = self.client.get(reverse("metrics:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/metric_list.html", [template.name for template in response.templates])

    def test_community_list_uses_community_template(self):
        response = self.client.get(reverse("communities:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/community_list.html", [template.name for template in response.templates])


class LandingPageTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_landing_page_status_and_template(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/landing.html", [template.name for template in response.templates])

    def test_landing_page_root_url(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/landing.html", [template.name for template in response.templates])

    def test_landing_page_contains_admin_link(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertContains(response, reverse("admin:index"))

    def test_landing_page_contains_general_info(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertContains(response, "Nutriacción")
        self.assertContains(response, "Qachuu Aloom")


class MetricCreationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(responsible_name="Test Family")
        self.patient = Patient.objects.create(
            code="P001", name="Test Patient", gender="M", dob=datetime.date(2020, 1, 1), family=self.family
        )
        self.client = Client()

    def test_create_metric_with_existing_visit(self):
        visit = Visit.objects.create(patient=self.patient)
        url = reverse("metrics:new")
        data = {
            "visit": visit.id,
            "weight": 10.5,
            "height": 75.0,
            "standing_or_upright": True,
            "muac": 12.0,
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Metric.objects.filter(visit=visit).count(), 1)

    def test_create_metric_with_implicit_visit(self):
        url = reverse("metrics:new")
        data = {
            "patient": self.patient.id,
            "weight": 11.0,
            "height": 80.0,
            "standing_or_upright": True,
            "muac": 13.0,
        }
        self.assertEqual(Visit.objects.filter(patient=self.patient).count(), 0)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        self.assertEqual(Visit.objects.filter(patient=self.patient).count(), 1)
        visit = Visit.objects.get(patient=self.patient)
        self.assertEqual(Metric.objects.filter(visit=visit).count(), 1)
        metric = Metric.objects.get(visit=visit)
        self.assertEqual(metric.weight, 11.0)

    def test_create_metric_fails_without_visit_or_patient(self):
        url = reverse("metrics:new")
        data = {"weight": 12.0, "height": 85.0, "standing_or_upright": True, "muac": 14.0}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], None, "Debe seleccionar una visita existente o un paciente para crear una nueva visita."
        )


class CommunityModelAndRelationshipTests(TestCase):
    def setUp(self):
        self.community = Community.objects.create(
            name="Chicruz", municipality="Rabinal", department="Baja Verapaz", contact_person="María López"
        )
        self.family = Family.objects.create(responsible_name="Familia Pérez", community=self.community)
        self.patient = Patient.objects.create(
            code="CHI001", name="Juanito Pérez", gender="M", dob=datetime.date(2022, 5, 10), family=self.family
        )

    def test_community_string_representation(self):
        self.assertEqual(str(self.community), "Chicruz (Rabinal)")

    def test_patient_community_property(self):
        self.assertEqual(self.patient.community, self.community)

    def test_patient_without_family_has_none_community(self):
        lonely_patient = Patient.objects.create(
            code="CHI002", name="Niño Solitario", gender="F", dob=datetime.date(2023, 1, 1), family=None
        )
        self.assertIsNone(lonely_patient.community)

    def test_multiple_visit_creation_and_str(self):
        mv = MultipleVisit.objects.create(
            community=self.community,
            date=timezone.now(),
            responsible_name="Promotor Qachuu",
            notes="Jornada de pesaje mensual",
        )
        self.assertIn("Jornada Chicruz", str(mv))
        self.assertEqual(mv.community, self.community)


class CommunityViewsTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(
            name="Pachoj", municipality="Rabinal", department="Baja Verapaz", contact_person="Pedro Gómez"
        )
        self.family = Family.objects.create(responsible_name="Familia Gómez", community=self.community)
        self.patient = Patient.objects.create(
            code="PAC001", name="Anita Gómez", gender="F", dob=datetime.date(2023, 3, 15), family=self.family
        )

    def test_community_list_view(self):
        response = self.client.get(reverse("communities:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pachoj")
        self.assertContains(response, "Pedro Gómez")

    def test_community_detail_roster_view(self):
        visit = Visit.objects.create(patient=self.patient, date=timezone.now())
        Metric.objects.create(visit=visit, weight=12.5, height=88.0, standing_or_upright=True)

        response = self.client.get(reverse("communities:detail", args=[self.community.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/community_roster.html", [t.name for t in response.templates])
        self.assertContains(response, "Anita Gómez")
        self.assertContains(response, "PAC001")
        # In Spanish locale float may be formatted as 12,5 or 12.5
        content = response.content.decode("utf-8")
        self.assertTrue("12.5" in content or "12,5" in content)
        self.assertTrue("88.0" in content or "88,0" in content or "88" in content)

    def test_community_detail_csv_export(self):
        visit = Visit.objects.create(patient=self.patient, date=timezone.now())
        Metric.objects.create(visit=visit, weight=12.5, height=88.0, standing_or_upright=True)

        response = self.client.get(reverse("communities:detail", args=[self.community.id]) + "?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode("utf-8")
        self.assertIn("PAC001", content)
        self.assertIn("Anita Gómez", content)

    def test_community_create_view(self):
        response = self.client.post(
            reverse("communities:new"),
            {
                "name": "Chicacao",
                "municipality": "Rabinal",
                "department": "Baja Verapaz",
                "contact_person": "Luisa Chen",
                "notes": "Comunidad rural",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Community.objects.filter(name="Chicacao").exists())

    def test_community_update_view(self):
        response = self.client.post(
            reverse("communities:edit", args=[self.community.id]),
            {
                "name": "Pachoj Actualizado",
                "municipality": "Rabinal",
                "department": "Baja Verapaz",
                "contact_person": "Pedro Gómez Modificado",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.community.refresh_from_db()
        self.assertEqual(self.community.name, "Pachoj Actualizado")
        self.assertEqual(self.community.contact_person, "Pedro Gómez Modificado")

    def test_community_delete_view(self):
        response = self.client.post(reverse("communities:delete", args=[self.community.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Community.objects.filter(id=self.community.id).exists())


class CommunityFilteringTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.com1 = Community.objects.create(name="Comunidad Uno")
        self.com2 = Community.objects.create(name="Comunidad Dos")
        self.fam1 = Family.objects.create(responsible_name="Fam Uno", community=self.com1)
        self.fam2 = Family.objects.create(responsible_name="Fam Dos", community=self.com2)
        self.p1 = Patient.objects.create(
            code="C1P1", name="Niño Uno", gender="M", dob=datetime.date(2021, 1, 1), family=self.fam1
        )
        self.p2 = Patient.objects.create(
            code="C2P1", name="Niño Dos", gender="F", dob=datetime.date(2021, 2, 1), family=self.fam2
        )
        self.v1 = Visit.objects.create(patient=self.p1)
        self.v2 = Visit.objects.create(patient=self.p2)

    def test_filter_patients_by_community(self):
        response = self.client.get(reverse("patients:list") + f"?community={self.com1.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Niño Uno")
        self.assertNotContains(response, "Niño Dos")

    def test_filter_visits_by_community(self):
        response = self.client.get(reverse("visits:list") + f"?community={self.com2.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Niño Dos")
        self.assertNotContains(response, "Niño Uno")


class PatientFormCommunityTests(TestCase):
    def setUp(self):
        self.community = Community.objects.create(name="Plan de Sánchez")

    def test_create_patient_with_new_family_and_existing_community(self):
        form_data = {
            "code": "PDS001",
            "name": "Carlos Sánchez",
            "gender": "M",
            "dob": "2022-04-10",
            "new_family_name": "Familia Sánchez",
            "community": self.community.id,
        }
        form = PatientForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save()
        self.assertEqual(patient.family.responsible_name, "Familia Sánchez")
        self.assertEqual(patient.family.community, self.community)
        self.assertEqual(patient.community, self.community)

    def test_create_patient_with_new_community_and_new_family(self):
        form_data = {
            "code": "NUE001",
            "name": "Elena Nueva",
            "gender": "F",
            "dob": "2023-01-15",
            "new_family_name": "Familia Nueva",
            "new_community_name": "Aldea Nueva Esperanza",
        }
        form = PatientForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save()
        self.assertEqual(patient.community.name, "Aldea Nueva Esperanza")


class MassMeasurementAndJornadaTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(name="Chiticoy", municipality="Rabinal")
        self.fam1 = Family.objects.create(responsible_name="Familia A", community=self.community)
        self.fam2 = Family.objects.create(responsible_name="Familia B", community=self.community)
        self.fam3 = Family.objects.create(responsible_name="Familia C", community=self.community)

        self.p1 = Patient.objects.create(
            code="CHI01", name="Niño A", gender="M", dob=datetime.date(2022, 1, 1), family=self.fam1
        )
        self.p2 = Patient.objects.create(
            code="CHI02", name="Niño B", gender="F", dob=datetime.date(2023, 1, 1), family=self.fam2
        )
        self.p3 = Patient.objects.create(
            code="CHI03", name="Niño C (Ausente)", gender="M", dob=datetime.date(2024, 1, 1), family=self.fam3
        )

    def test_mass_visit_get_renders_formset_for_community_patients(self):
        response = self.client.get(reverse("communities:mass_visit", args=[self.community.id]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/community_mass_visit.html", [t.name for t in response.templates])
        self.assertContains(response, "Niño A")
        self.assertContains(response, "Niño B")
        self.assertContains(response, "Niño C (Ausente)")

    def test_mass_visit_post_batch_saves_measurements_and_skips_empty(self):
        data = {
            "date": "2026-08-17",
            "responsible_name": "Promotor Test",
            "notes": "Jornada exitosa",
            "rows-TOTAL_FORMS": "3",
            "rows-INITIAL_FORMS": "3",
            "rows-MIN_NUM_FORMS": "0",
            "rows-MAX_NUM_FORMS": "1000",
            # Row 0: Child A measured
            "rows-0-patient_id": str(self.p1.id),
            "rows-0-weight": "14.2",
            "rows-0-height": "95.5",
            "rows-0-standing_or_upright": "True",
            "rows-0-muac": "14.5",
            "rows-0-edema": False,
            "rows-0-notes": "Buen estado",
            # Row 1: Child B measured with edema
            "rows-1-patient_id": str(self.p2.id),
            "rows-1-weight": "10.1",
            "rows-1-height": "80.0",
            "rows-1-standing_or_upright": "False",
            "rows-1-muac": "12.0",
            "rows-1-edema": True,
            "rows-1-notes": "",
            # Row 2: Child C left blank (unattended)
            "rows-2-patient_id": str(self.p3.id),
            "rows-2-weight": "",
            "rows-2-height": "",
            "rows-2-standing_or_upright": "",
            "rows-2-muac": "",
            "rows-2-edema": False,
            "rows-2-notes": "",
        }

        response = self.client.post(reverse("communities:mass_visit", args=[self.community.id]), data)
        self.assertEqual(response.status_code, 302)

        # Check MultipleVisit created
        self.assertEqual(MultipleVisit.objects.filter(community=self.community).count(), 1)
        mv = MultipleVisit.objects.get(community=self.community)
        self.assertEqual(mv.responsible_name, "Promotor Test")

        # Visits created: 2 visits (Child A and Child B), Child C skipped
        self.assertEqual(Visit.objects.filter(multiple_visit=mv).count(), 2)
        self.assertEqual(Visit.objects.filter(patient=self.p1).count(), 1)
        self.assertEqual(Visit.objects.filter(patient=self.p2).count(), 1)
        self.assertEqual(Visit.objects.filter(patient=self.p3).count(), 0)

        # Verify Metrics and calculated Z-scores
        v1 = Visit.objects.get(patient=self.p1)
        m1 = Metric.objects.get(visit=v1)
        self.assertEqual(m1.weight, 14.2)
        self.assertEqual(m1.height, 95.5)
        self.assertIsNotNone(m1.wfaz)
        self.assertIsNotNone(m1.hfaz)
        self.assertIsNotNone(m1.wfhz)

        v2 = Visit.objects.get(patient=self.p2)
        m2 = Metric.objects.get(visit=v2)
        self.assertEqual(m2.weight, 10.1)
        self.assertTrue(m2.edema)

    def test_mass_measurement_row_form_validation(self):
        # Weight provided without height -> invalid
        form1 = MassMeasurementRowForm(data={"patient_id": self.p1.id, "weight": 10.0, "height": ""})
        self.assertFalse(form1.is_valid())

        # Height provided without weight -> invalid
        form2 = MassMeasurementRowForm(data={"patient_id": self.p1.id, "weight": "", "height": 80.0})
        self.assertFalse(form2.is_valid())

        # Both blank -> valid (will be skipped)
        form3 = MassMeasurementRowForm(data={"patient_id": self.p1.id, "weight": "", "height": ""})
        self.assertTrue(form3.is_valid())
        self.assertFalse(form3.has_data())

        # Both provided -> valid with data
        form4 = MassMeasurementRowForm(data={"patient_id": self.p1.id, "weight": 11.0, "height": 82.0})
        self.assertTrue(form4.is_valid())
        self.assertTrue(form4.has_data())


class NutritionalStatusHelperTests(TestCase):
    def test_status_for_none(self):
        status = get_nutritional_status(None)
        self.assertEqual(status["status"], "Sin datos")
        self.assertEqual(status["badge_class"], "secondary")

    def test_status_for_edema(self):
        family = Family.objects.create(responsible_name="Fam")
        patient = Patient.objects.create(code="P", name="P", gender="M", dob=datetime.date(2022, 1, 1), family=family)
        visit = Visit.objects.create(patient=patient)
        metric = Metric.objects.create(visit=visit, weight=10.0, height=80.0, edema=True)
        status = get_nutritional_status(metric)
        self.assertIn("Desnutrición Aguda Severa (Edema)", status["status"])
        self.assertEqual(status["badge_class"], "danger")

    def test_status_for_weight_loss_alert(self):
        family = Family.objects.create(responsible_name="Fam")
        patient = Patient.objects.create(code="P", name="P", gender="M", dob=datetime.date(2022, 1, 1), family=family)
        v1 = Visit.objects.create(patient=patient, date=timezone.now() - datetime.timedelta(days=30))
        m1 = Metric.objects.create(visit=v1, weight=12.0, height=80.0)
        v2 = Visit.objects.create(patient=patient, date=timezone.now())
        m2 = Metric.objects.create(visit=v2, weight=11.5, height=81.0)
        status = get_nutritional_status(m2, previous_metric=m1)
        self.assertIn("Alerta: Pérdida de Peso", status["status"])


class HouseholdStatusHistoryTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(responsible_name="Familia Test")
        self.well = WaterSource.objects.create(name="Pozo")
        self.river = WaterSource.objects.create(name="Río")
        # Created out of chronological order to prove lookups sort by recorded_at, not insertion order.
        HouseholdStatus.objects.create(family=self.family, recorded_at=datetime.date(2024, 6, 1), water_source=self.river)
        HouseholdStatus.objects.create(family=self.family, recorded_at=datetime.date(2023, 1, 1), water_source=self.well)

    def test_status_as_of_picks_the_snapshot_in_effect_on_that_date(self):
        status = self.family.status_as_of(datetime.date(2023, 6, 1))
        self.assertEqual(status.water_source, self.well)

    def test_status_as_of_picks_the_later_snapshot_once_it_applies(self):
        status = self.family.status_as_of(datetime.date(2024, 8, 1))
        self.assertEqual(status.water_source, self.river)

    def test_status_as_of_before_any_snapshot_is_none(self):
        status = self.family.status_as_of(datetime.date(2022, 1, 1))
        self.assertIsNone(status)

    def test_current_status_is_the_most_recent_snapshot(self):
        self.assertEqual(self.family.current_status.water_source, self.river)


class LongformExportTests(TestCase):
    def setUp(self):
        self.community = Community.objects.create(name="Aldea Test")
        self.family = Family.objects.create(responsible_name="Familia Test", community=self.community)
        self.well = WaterSource.objects.create(name="Pozo")
        self.river = WaterSource.objects.create(name="Río")
        HouseholdStatus.objects.create(family=self.family, recorded_at=datetime.date(2024, 6, 1), water_source=self.river)
        HouseholdStatus.objects.create(family=self.family, recorded_at=datetime.date(2023, 1, 1), water_source=self.well)

        self.patient = Patient.objects.create(
            code="C1", name="Niño Test", gender="M", dob=datetime.date(2022, 1, 1), family=self.family
        )
        self.visit1 = Visit.objects.create(patient=self.patient, date=datetime.datetime(2023, 6, 1))
        Metric.objects.create(visit=self.visit1, weight=10.0, height=75.0, standing_or_upright=False)
        EnvironmentMetric.objects.create(visit=self.visit1, dietary_diversity_score=4, breastfeeding=True)

        self.visit2 = Visit.objects.create(patient=self.patient, date=datetime.datetime(2024, 8, 1))
        Metric.objects.create(visit=self.visit2, weight=13.0, height=88.0, standing_or_upright=True)

    def test_one_row_per_visit(self):
        df = build_longform_dataframe()
        self.assertEqual(len(df), 2)

    def test_visit_number_and_days_since_first_visit(self):
        df = build_longform_dataframe()
        row1 = df[df["visit_id"] == self.visit1.id].iloc[0]
        row2 = df[df["visit_id"] == self.visit2.id].iloc[0]
        self.assertEqual(row1["visit_number"], 1)
        self.assertEqual(row2["visit_number"], 2)
        self.assertEqual(row1["days_since_first_visit"], 0)
        self.assertEqual(row2["days_since_first_visit"], (datetime.date(2024, 8, 1) - datetime.date(2023, 6, 1)).days)

    def test_household_status_is_joined_as_of_the_visit_date(self):
        df = build_longform_dataframe()
        row1 = df[df["visit_id"] == self.visit1.id].iloc[0]
        row2 = df[df["visit_id"] == self.visit2.id].iloc[0]
        self.assertEqual(row1["water_source"], "Pozo")
        self.assertEqual(row2["water_source"], "Río")

    def test_environment_metric_fields_are_present(self):
        df = build_longform_dataframe()
        row1 = df[df["visit_id"] == self.visit1.id].iloc[0]
        row2 = df[df["visit_id"] == self.visit2.id].iloc[0]
        self.assertEqual(row1["dietary_diversity_score"], 4)
        self.assertTrue(row1["breastfeeding"])
        self.assertTrue(pd.isna(row2["dietary_diversity_score"]))

    def test_no_identifying_fields_are_exported(self):
        df = build_longform_dataframe()
        for leaky_column in ("name", "mother_name", "code", "responsible_name", "contact_person"):
            self.assertNotIn(leaky_column, df.columns)


class CsrfSettingsTests(TestCase):
    def test_csrf_trusted_origins_is_configured(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, "CSRF_TRUSTED_ORIGINS"))
        self.assertIsInstance(settings.CSRF_TRUSTED_ORIGINS, list)

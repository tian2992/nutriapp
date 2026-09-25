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

    def assertContainsFloats(self, response, *values, status_code=200):
        if status_code is not None:
            self.assertEqual(response.status_code, status_code)
        content = response.content.decode("utf-8")
        for val in values:
            val_dot = str(val)
            val_comma = val_dot.replace(".", ",")
            candidates = [val_dot, val_comma]
            if val_dot.endswith(".0"):
                candidates.append(val_dot[:-2])
            self.assertTrue(
                any(c in content for c in candidates),
                f"None of {candidates} found in response content",
            )


class ListTemplateTests(BaseAuthenticatedTestCase):
    def test_patient_list_uses_patient_template(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/patient_list.html")

    def test_metric_list_uses_metric_template(self):
        response = self.client.get(reverse("metrics:list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/metric_list.html")

    def test_community_list_uses_community_template(self):
        response = self.client.get(reverse("communities:list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/community_list.html")


class FloatFormattingViewsTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(name="San Gabriel", municipality="Rabinal")
        self.family = Family.objects.create(responsible_name="Familia Cortez", community=self.community)
        self.patient = Patient.objects.create(
            code="SG01",
            name="Elena Cortez",
            gender="F",
            dob=datetime.date(2022, 1, 1),
            family=self.family,
        )
        self.visit = Visit.objects.create(patient=self.patient, date=timezone.now())
        self.metric = Metric.objects.create(
            visit=self.visit,
            weight=12.3456,
            height=85.6789,
            muac=14.5,
            standing_or_upright=True,
        )

    def test_metric_list_floatformat(self):
        response = self.client.get(reverse("metrics:list"))
        self.assertContainsFloats(response, "12.35", "85.68")

    def test_metric_detail_floatformat(self):
        response = self.client.get(reverse("metrics:detail", args=[self.metric.id]))
        self.assertContainsFloats(response, "12.35", "85.68", "14.50")

    def test_visit_detail_floatformat(self):
        response = self.client.get(reverse("visits:detail", args=[self.visit.id]))
        self.assertContainsFloats(response, "12.35", "85.68")

    def test_patient_detail_floatformat(self):
        response = self.client.get(reverse("patients:detail", args=[self.patient.id]))
        self.assertContainsFloats(response, "12.35", "85.68")

    def test_community_roster_floatformat(self):
        response = self.client.get(reverse("communities:detail", args=[self.community.id]))
        self.assertContainsFloats(response, "12.35", "85.68")


class PatientListMeasurementAndFamilyTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(name="Nimacabaj", municipality="Rabinal")
        self.family = Family.objects.create(responsible_name="Familia López", community=self.community)
        self.patient = Patient.objects.create(
            code="NIM01",
            name="Ana López",
            gender="F",
            dob=datetime.date(2021, 5, 1),
            family=self.family,
        )
        for weight, height in ((8.5, 70.0), (9.0, 72.0), (9.5, 74.0)):
            visit = Visit.objects.create(patient=self.patient)
            Metric.objects.create(visit=visit, weight=weight, height=height, standing_or_upright=True)

    def test_patient_list_shows_measurement_count(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        patient = response.context["object_list"].get(pk=self.patient.pk)
        self.assertEqual(patient.measurement_count, 3)
        self.assertContains(response, "Mediciones")
        self.assertContains(response, ">3</td>", html=False)

    def test_patient_list_links_to_family(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        family_url = reverse("patients:family", args=[self.family.id])
        self.assertContains(response, family_url)
        self.assertContains(response, "Familia López")

    def test_family_detail_lists_children_and_counts(self):
        response = self.client.get(reverse("patients:family", args=[self.family.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/family_detail.html")
        self.assertContains(response, "Ana López")
        self.assertContains(response, reverse("patients:detail", args=[self.patient.id]))
        self.assertContains(response, ">3</td>", html=False)

class LandingPageTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_landing_page_status_and_template(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/landing.html")

    def test_landing_page_root_url(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anthrocalc/landing.html")

    def test_landing_page_contains_admin_link(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertContains(response, reverse("admin:index"))

    def test_landing_page_contains_general_info(self):
        response = self.client.get(reverse("antrobase:home"))
        self.assertContains(response, "Nutriacción")
        self.assertContains(response, "Qachuu Aloom")


class MetricCreationTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.family = Family.objects.create(responsible_name="Test Family")
        self.patient = Patient.objects.create(
            code="P001", name="Test Patient", gender="M", dob=datetime.date(2020, 1, 1), family=self.family
        )

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

    def test_create_metric_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse("metrics:new"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])


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
        self.assertTemplateUsed(response, "anthrocalc/community_roster.html")
        self.assertContains(response, "Anita Gómez")
        self.assertContains(response, "PAC001")
        self.assertContainsFloats(response, "12.5", "88.0")

    def test_community_detail_csv_export(self):
        visit = Visit.objects.create(patient=self.patient, date=timezone.now())
        Metric.objects.create(visit=visit, weight=12.5, height=88.0, standing_or_upright=True)

        response = self.client.get(reverse("communities:detail", args=[self.community.id]) + "?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertContains(response, "PAC001")
        self.assertContains(response, "Anita Gómez")

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

    def test_code_is_optional_and_autogenerated(self):
        form_data = {
            "code": "",
            "name": "Sin Código",
            "gender": "F",
            "dob": "2022-06-01",
            "new_family_name": "Familia Auto",
            "community": self.community.id,
        }
        form = PatientForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        patient = form.save()
        # Rabinal (default) + Plan de Sánchez → QARABPLA001
        self.assertEqual(patient.code, "QARABPLA001")


class PatientCodeGenerationTests(TestCase):
    def test_segment_helpers_trim_accents_and_pad(self):
        from .patient_codes import community_code, municipality_code

        self.assertEqual(municipality_code("Rabinal"), "RAB")
        self.assertEqual(community_code("Nimacabaj"), "NIM")
        self.assertEqual(community_code("Plan de Sánchez"), "PLA")
        self.assertEqual(municipality_code("X"), "XXX")
        self.assertEqual(community_code(""), "XXX")

    def test_segment_helpers_prefer_optional_map(self):
        from .patient_codes import code_prefix_for_community, community_code, municipality_code

        self.assertEqual(community_code("Plan de Sánchez", code_map={"Plan de Sánchez": "PDS"}), "PDS")
        self.assertEqual(municipality_code("Rabinal", code_map={"Rabinal": "RBN"}), "RBN")
        community = Community(name="Plan de Sánchez", municipality="Rabinal")
        self.assertEqual(
            code_prefix_for_community(
                community,
                municipality_map={"Rabinal": "RBN"},
                community_map={"Plan de Sánchez": "PDS"},
            ),
            "QARBNPDS",
        )

    def test_generate_matches_historical_prefix_and_sequences(self):
        from .patient_codes import generate_patient_code

        community = Community.objects.create(name="Nimacabaj", municipality="Rabinal")
        family = Family.objects.create(responsible_name="Fam", community=community)
        Patient.objects.create(
            code="QARABNIM001", name="A", gender="M", dob=datetime.date(2020, 1, 1), family=family
        )
        self.assertEqual(generate_patient_code(community), "QARABNIM002")

    def test_patient_save_autogenerates_when_code_blank(self):
        community = Community.objects.create(name="Nimacabaj", municipality="Rabinal")
        family = Family.objects.create(responsible_name="Fam", community=community)
        patient = Patient.objects.create(
            code="", name="Auto", gender="F", dob=datetime.date(2021, 1, 1), family=family
        )
        self.assertEqual(patient.code, "QARABNIM001")

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
        self.assertTemplateUsed(response, "anthrocalc/community_mass_visit.html")
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
        self.visit1 = Visit.objects.create(patient=self.patient, date=timezone.make_aware(datetime.datetime(2023, 6, 1)))
        Metric.objects.create(visit=self.visit1, weight=10.0, height=75.0, standing_or_upright=False)
        EnvironmentMetric.objects.create(visit=self.visit1, dietary_diversity_score=4, breastfeeding=True)

        self.visit2 = Visit.objects.create(patient=self.patient, date=timezone.make_aware(datetime.datetime(2024, 8, 1)))
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


class WhoReferenceTests(TestCase):
    def test_sex_normalization(self):
        from .who_reference import normalize_sex
        self.assertEqual(normalize_sex("male"), "male")
        self.assertEqual(normalize_sex("M"), "male")
        self.assertEqual(normalize_sex("masculino"), "male")
        self.assertEqual(normalize_sex("female"), "female")
        self.assertEqual(normalize_sex("F"), "female")
        self.assertEqual(normalize_sex("femenino"), "female")
        with self.assertRaises(ValueError):
            normalize_sex("invalid")

    def test_z_zero_equals_median_m(self):
        from .who_reference import reference_band, get_lms_for_point
        # Test HAZ at 12 months for male
        lms_haz = get_lms_for_point("hfa", "male", 12)
        band_haz = reference_band("hfa", "male", [12])[0]
        self.assertAlmostEqual(band_haz["0"], float(lms_haz["m"]), places=4)

        # Test WAZ at 24 months for female
        lms_waz = get_lms_for_point("wfa", "female", 24)
        band_waz = reference_band("wfa", "female", [24])[0]
        self.assertAlmostEqual(band_waz["0"], float(lms_waz["m"]), places=4)

        # Test WHZ at 80cm for male
        lms_whz = get_lms_for_point("wfh", "male", 80.0)
        band_whz = reference_band("wfh", "male", [80.0])[0]
        self.assertAlmostEqual(band_whz["0"], float(lms_whz["m"]), places=4)

        # Test WFL at 60cm for female
        lms_wfl = get_lms_for_point("wfl", "female", 60.0)
        band_wfl = reference_band("wfl", "female", [60.0])[0]
        self.assertAlmostEqual(band_wfl["0"], float(lms_wfl["m"]), places=4)

    def test_roundtrip_against_pygrowup(self):
        import pygrowup
        from .who_reference import reference_band

        # 1. Height-for-age (HAZ) at 12 months (male)
        obs_haz = pygrowup.Observation(sex="male", age_in_months=12)
        band_haz = reference_band("hfa", "male", [12])[0]
        for z_key, expected_z in [("-2SD", -2.0), ("-1SD", -1.0), ("0", 0.0), ("+1SD", 1.0), ("+2SD", 2.0)]:
            val = band_haz[z_key]
            calc_z = float(obs_haz.lhfa(val, recumbent=False, auto_adjust=False))
            self.assertAlmostEqual(calc_z, expected_z, delta=0.05)

        # 2. Weight-for-age (WAZ) at 18 months (female)
        obs_waz = pygrowup.Observation(sex="female", age_in_months=18)
        band_waz = reference_band("wfa", "female", [18])[0]
        for z_key, expected_z in [("-2SD", -2.0), ("-1SD", -1.0), ("0", 0.0), ("+1SD", 1.0), ("+2SD", 2.0)]:
            val = band_waz[z_key]
            calc_z = float(obs_waz.wfa(val))
            self.assertAlmostEqual(calc_z, expected_z, delta=0.05)

        # 3. Weight-for-height (WHZ) at 85cm (male)
        obs_whz = pygrowup.Observation(sex="male", age_in_months=24)
        band_whz = reference_band("wfh", "male", [85.0])[0]
        for z_key, expected_z in [("-2SD", -2.0), ("-1SD", -1.0), ("0", 0.0), ("+1SD", 1.0), ("+2SD", 2.0)]:
            val = band_whz[z_key]
            calc_z = float(obs_whz.wfh(val, 85.0))
            self.assertAlmostEqual(calc_z, expected_z, delta=0.05)


class GrowthChartTests(BaseAuthenticatedTestCase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(name="Chicacao", municipality="Rabinal")
        self.family = Family.objects.create(responsible_name="Familia Perez", community=self.community)
        self.patient = Patient.objects.create(
            code="CHI01",
            name="Carlos Perez",
            gender="M",
            dob=datetime.date(2022, 1, 1),
            family=self.family,
        )
        # Create 3 visits with metrics
        self.v1 = Visit.objects.create(
            patient=self.patient,
            date=timezone.make_aware(datetime.datetime(2022, 7, 1)),
        )
        Metric.objects.create(visit=self.v1, weight=7.5, height=67.0, standing_or_upright=False)

        self.v2 = Visit.objects.create(
            patient=self.patient,
            date=timezone.make_aware(datetime.datetime(2023, 1, 1)),
        )
        Metric.objects.create(visit=self.v2, weight=9.5, height=75.0, standing_or_upright=True)

        self.v3 = Visit.objects.create(
            patient=self.patient,
            date=timezone.make_aware(datetime.datetime(2023, 7, 1)),
        )
        Metric.objects.create(visit=self.v3, weight=11.0, height=84.0, standing_or_upright=True)

    def test_compute_patient_growth_series_decoupled(self):
        from .patient_graph import compute_patient_growth_series

        for ind in ("hfa", "wfa", "wfh"):
            data = compute_patient_growth_series(self.patient, indicator=ind)
            self.assertIn("series", data)
            self.assertIn("title", data)
            self.assertIn("xlabel", data)
            self.assertIn("ylabel", data)

            labels = [s["label"] for s in data["series"]]
            self.assertIn("+2 SD", labels)
            self.assertIn("+1 SD", labels)
            self.assertIn("0 (Mediana OMS)", labels)
            self.assertIn("-1 SD", labels)
            self.assertIn("-2 SD", labels)
            self.assertTrue(any("Mediciones" in lbl for lbl in labels))

    def test_compute_group_growth_series_stub(self):
        from .patient_graph import compute_group_growth_series

        group_data = compute_group_growth_series([self.patient], indicator="hfa", group_name="Comunidad Test")
        self.assertIn("series", group_data)
        self.assertIn("Crecimiento Grupal", group_data["title"])
        self.assertTrue(len(group_data["series"]) >= 4)

    def test_render_chart_to_bytes(self):
        from .patient_graph import render_chart_to_bytes

        series_list = [
            {"label": "Test Series", "xs": [0, 1, 2], "ys": [10, 20, 30], "style": {"color": "blue"}}
        ]
        png_bytes = render_chart_to_bytes(series_list, title="Test Chart", xlabel="X", ylabel="Y")
        self.assertIsInstance(png_bytes, bytes)
        self.assertTrue(png_bytes.startswith(b"\x89PNG"))

    def test_graph_for_person_view(self):
        # Without person_id -> 400
        res = self.client.get(reverse("antrobase:personal_progress"))
        self.assertEqual(res.status_code, 400)

        # With person_id for each indicator -> 200 image/png
        for ind in ("hfa", "wfa", "wfh"):
            url = f"{reverse('antrobase:personal_progress')}?person_id={self.patient.id}&indicator={ind}"
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res["Content-Type"], "image/png")
            self.assertTrue(res.content.startswith(b"\x89PNG"))

    def test_patient_detail_template_shows_growth_charts(self):
        url = reverse("patients:detail", args=[self.patient.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("Gráficas de Crecimiento", content)
        self.assertIn(f"personal_progress.png?person_id={self.patient.id}&indicator=hfa", content)
        self.assertIn(f"personal_progress.png?person_id={self.patient.id}&indicator=wfa", content)
        self.assertIn(f"personal_progress.png?person_id={self.patient.id}&indicator=wfh", content)

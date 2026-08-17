from datetime import date

from django.template.backends import django
from django.test import Client, TestCase
from django.urls import reverse

from .models import Family, Metric, Patient, Visit


class ListTemplateTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_patient_list_uses_patient_template(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/patient_list.html", [template.name for template in response.templates])

    def test_metric_list_uses_metric_template(self):
        response = self.client.get(reverse("metrics:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/metric_list.html", [template.name for template in response.templates])


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
            code="P001", name="Test Patient", gender="M", dob=date(2020, 1, 1), family=self.family
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
            "eye_signs": "none",
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
            "eye_signs": "none",
        }
        # Visit count before
        self.assertEqual(Visit.objects.filter(patient=self.patient).count(), 0)

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        # Check if Visit was created
        self.assertEqual(Visit.objects.filter(patient=self.patient).count(), 1)
        visit = Visit.objects.get(patient=self.patient)

        # Check if Metric was created and linked to the new Visit
        self.assertEqual(Metric.objects.filter(visit=visit).count(), 1)
        metric = Metric.objects.get(visit=visit)
        self.assertEqual(metric.weight, 11.0)

    def test_create_metric_fails_without_visit_or_patient(self):
        url = reverse("metrics:new")
        data = {"weight": 12.0, "height": 85.0, "standing_or_upright": True, "muac": 14.0, "eye_signs": "none"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertFormError(
            response.context["form"], None, "Debe seleccionar una visita existente o un paciente para crear una nueva visita."
        )

from datetime import date

from django.contrib.auth import get_user_model
from django.template.backends import django
from django.test import Client, TestCase
from django.urls import reverse

from .models import Family, Metric, Patient, Visit


class ListTemplateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_superuser(username="admin", password="secret123")
        self.client.force_login(self.user)

    def test_patient_list_uses_patient_template(self):
        response = self.client.get(reverse("patients:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/patient_list.html", [template.name for template in response.templates])

    def test_metric_list_uses_metric_template(self):
        response = self.client.get(reverse("metrics:list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("anthrocalc/metric_list.html", [template.name for template in response.templates])


class UserFamilyAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = get_user_model().objects.create_user(username="worker", password="secret123")
        self.other_user = get_user_model().objects.create_user(username="other", password="secret123")

        self.family_a = Family.objects.create(responsible_name="Family A")
        self.family_a.allowed_users.add(self.user)
        self.patient_a = Patient.objects.create(
            code="P001", name="Patient A", gender="M", dob=date(2020, 1, 1), family=self.family_a
        )

        self.family_b = Family.objects.create(responsible_name="Family B")
        self.family_b.allowed_users.add(self.other_user)
        self.patient_b = Patient.objects.create(
            code="P002", name="Patient B", gender="F", dob=date(2021, 2, 2), family=self.family_b
        )

    def test_non_staff_user_sees_only_assigned_family_patients(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.patient_a.name)
        self.assertNotContains(response, self.patient_b.name)

    def test_non_staff_user_cannot_access_unassigned_patient_detail(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("patients:detail", args=[self.patient_b.id]))

        self.assertEqual(response.status_code, 403)

    def test_new_patient_created_for_current_user_family(self):
        self.client.force_login(self.user)
        data = {
            "code": "P999",
            "name": "New Patient",
            "gender": "M",
            "dob": "2022-03-03",
            "new_family_name": "New Assigned Family",
        }

        response = self.client.post(reverse("patients:new"), data)

        self.assertEqual(response.status_code, 302)
        created_patient = Patient.objects.get(code="P999")
        self.assertTrue(created_patient.family.allowed_users.filter(pk=self.user.pk).exists())


class MetricCreationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(responsible_name="Test Family")
        self.patient = Patient.objects.create(
            code="P001", name="Test Patient", gender="M", dob=date(2020, 1, 1), family=self.family
        )
        self.client = Client()
        self.user = get_user_model().objects.create_superuser(username="admin", password="secret123")
        self.client.force_login(self.user)

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
        self.assertIn(
            "Debe seleccionar una visita existente o un paciente para crear una nueva visita.",
            response.context["form"].non_field_errors(),
        )

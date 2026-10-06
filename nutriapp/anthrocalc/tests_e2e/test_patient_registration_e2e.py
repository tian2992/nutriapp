"""E2E tests for new-patient registration (PatientCreation / patient_form.html).

- `test_register_new_child_with_new_family_and_community` registers a child
  whose name is not on file, in one POST.
- `test_registering_a_name_that_already_exists_surfaces_a_duplicate_warning`
  searches by name before create and expects a link to the existing patient
  (`docs/specs/buscar_paciente_existente.md`).
"""

import datetime

from anthrocalc.models import Community, Family, Patient

from .base import PlaywrightTestCase


class PatientRegistrationE2ETests(PlaywrightTestCase):
    def test_register_new_child_with_new_family_and_community(self):
        self.login_as_field_agent()
        self.page.goto(f"{self.live_server_url}/patient/new")

        self.page.fill("#id_name", "Carla Nueva")
        self.page.select_option("#id_gender", "F")
        self.page.fill("#id_dob", "2023-03-10")
        self.page.fill("#id_new_community_name", "Comunidad Nueva E2E")
        self.page.fill("#id_new_family_name", "Familia Nueva E2E")

        self.page.click("form button[type=submit], form input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        patient = Patient.objects.get(name="Carla Nueva")
        # Default municipio Rabinal + community "Comunidad..." → QARABCOM001
        self.assertEqual(patient.code, "QARABCOM001")
        self.assertIsNotNone(patient.family)
        self.assertEqual(patient.family.responsible_name, "Familia Nueva E2E")
        self.assertEqual(patient.family.community.name, "Comunidad Nueva E2E")

    def test_registering_a_name_that_already_exists_surfaces_a_duplicate_warning(self):
        self.login_as_field_agent()
        community = Community.objects.create(name="Comunidad Existente E2E")
        family = Family.objects.create(responsible_name="Familia Existente E2E", community=community)
        existing = Patient.objects.create(
            code="E2E-EXIST-01", name="Diego Repetido", gender="M", dob=datetime.date(2020, 5, 1), family=family
        )

        self.page.goto(f"{self.live_server_url}/patient/new")
        self.page.fill("#id_name", "Diego Repetido")
        # buscar_paciente_existente.md: a GET search re-renders the page
        # with matches and a link to the existing patient's detail page
        # before the create form can be submitted.
        self.page.click("#patient-search-submit")
        self.page.wait_for_load_state("networkidle")

        self.assertTrue(
            self.page.locator(f"a[href='/patient/{existing.id}']").count() > 0,
            "expected a link to the existing matching patient",
        )

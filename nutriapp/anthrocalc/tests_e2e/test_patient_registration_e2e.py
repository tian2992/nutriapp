"""E2E tests for new-patient registration (PatientCreation / patient_form.html).

Two different kinds of test on purpose:

- `test_register_new_child_with_new_family_and_community` exercises what
  already works today - a baseline. It should PASS right now.
- `test_registering_a_name_that_already_exists_surfaces_a_duplicate_warning`
  is spec-driven: it asserts the behavior described in
  docs/specs/buscar_paciente_existente.md, which is NOT implemented yet.
  It's marked `@unittest.expectedFailure` so the suite reports it as an
  expected failure (not a red X to chase) until that spec ships - and so
  it flips to "unexpected success" the moment it does, which is your
  signal to remove the decorator, not a bug.
"""

import datetime
import unittest

from anthrocalc.models import Community, Family, Patient

from .base import PlaywrightTestCase


class PatientRegistrationE2ETests(PlaywrightTestCase):
    def test_register_new_child_with_new_family_and_community(self):
        self.login_as_field_agent()
        self.page.goto(f"{self.live_server_url}/patient/new")

        self.page.fill("#id_code", "E2E-NEW-01")
        self.page.fill("#id_name", "Carla Nueva")
        # Free-text today (models.py:200 has no `choices` yet - see
        # validar_sexo_y_fecha_nacimiento.md). Once that spec lands this
        # becomes a <select> and this line needs `select_option` instead.
        self.page.fill("#id_gender", "F")
        self.page.fill("#id_dob", "2023-03-10")
        self.page.fill("#id_new_community_name", "Comunidad Nueva E2E")
        self.page.fill("#id_new_family_name", "Familia Nueva E2E")

        self.page.click("form button[type=submit], form input[type=submit]")
        self.page.wait_for_load_state("networkidle")

        patient = Patient.objects.get(code="E2E-NEW-01")
        self.assertEqual(patient.name, "Carla Nueva")
        self.assertIsNotNone(patient.family)
        self.assertEqual(patient.family.responsible_name, "Familia Nueva E2E")
        self.assertEqual(patient.family.community.name, "Comunidad Nueva E2E")

    @unittest.expectedFailure
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

"""Long-form (one row per visit) dataset for statistical modeling.

This module is the single source of truth for the analysis data contract.
Any export format (CSV, Parquet) or in-process bridge (rpy2, a notebook)
should call `build_longform_dataframe()` rather than re-deriving the joins
between Visit / Metric / EnvironmentMetric / Family / HouseholdStatus.

No directly-identifying fields (names, codes, contact info) are included
by design - only surrogate integer ids, which are safe to use as grouping
factors for mixed models (patient nested in family nested in community).

See docs/longform_dataset.md for the column dictionary.
"""

import pandas as pd

from .person_utils import calculate_age_at_date
from .models import Visit

LONGFORM_COLUMNS = [
    "visit_id",
    "patient_id",
    "family_id",
    "community_id",
    "municipality",
    "department",
    "gender",
    "age_days",
    "age_months",
    "visit_date",
    "visit_number",
    "days_since_first_visit",
    "weight",
    "height",
    "muac",
    "standing_or_upright",
    "wfaz",
    "hfaz",
    "wfhz",
    "bmi_age",
    "edema",
    "diarrhea",
    "intractable_vomiting",
    "convulsions",
    "lethargy_not_alert",
    "unconsciousness",
    "hypoglycemia",
    "high_fever",
    "hypothermia",
    "severe_dehydration",
    "lower_respiratory_tract_infection",
    "severe_anemia",
    "eye_signs_vit_a",
    "skin_lesions",
    "dietary_diversity_score",
    "breastfeeding",
    "immunization_up_to_date",
    "recent_illness",
    "recent_illness_type",
    "water_source",
    "sanitation_type",
    "floor_material",
    "wall_material",
    "roof_material",
    "household_income_proxy",
    "household_status_recorded_at",
    "household_status_age_days",
]


def build_longform_dataframe():
    """Return one row per Visit, ready for a mixed-model export.

    Household covariates are joined "as of" the visit date via
    `Family.status_as_of`, not the family's current status - so a growth
    curve reflects the conditions a child was actually living in at each
    measurement, not conditions recorded later.
    """
    visits = (
        Visit.objects.select_related(
            "patient",
            "patient__family",
            "patient__family__community",
            "metric",
        )
        .prefetch_related("environmentmetric_set")
        .order_by("patient_id", "date")
    )

    rows = []
    visit_number_by_patient = {}
    first_visit_date_by_patient = {}

    for visit in visits:
        patient = visit.patient
        family = patient.family
        community = family.community if family else None
        visit_date = visit.date.date() if hasattr(visit.date, "date") else visit.date

        visit_number_by_patient[patient.id] = visit_number_by_patient.get(patient.id, 0) + 1
        first_visit_date_by_patient.setdefault(patient.id, visit_date)

        age = calculate_age_at_date(patient, visit_date)
        metric = getattr(visit, "metric", None)
        env_metrics = list(visit.environmentmetric_set.all())
        env = env_metrics[0] if env_metrics else None
        household = family.status_as_of(visit_date) if family else None

        rows.append(
            {
                "visit_id": visit.id,
                "patient_id": patient.id,
                "family_id": family.id if family else None,
                "community_id": community.id if community else None,
                "municipality": community.municipality if community else None,
                "department": community.department if community else None,
                "gender": patient.gender,
                "age_days": age["dob_days"],
                "age_months": age["months_float"],
                "visit_date": visit_date,
                "visit_number": visit_number_by_patient[patient.id],
                "days_since_first_visit": (visit_date - first_visit_date_by_patient[patient.id]).days,
                "weight": metric.weight if metric else None,
                "height": metric.height if metric else None,
                "muac": metric.muac if metric else None,
                "standing_or_upright": metric.standing_or_upright if metric else None,
                "wfaz": metric.wfaz if metric else None,
                "hfaz": metric.hfaz if metric else None,
                "wfhz": metric.wfhz if metric else None,
                "bmi_age": metric.bmi_age if metric else None,
                "edema": metric.edema if metric else None,
                "diarrhea": metric.diarrhea if metric else None,
                "intractable_vomiting": metric.intractable_vomiting if metric else None,
                "convulsions": metric.convulsions if metric else None,
                "lethargy_not_alert": metric.lethargy_not_alert if metric else None,
                "unconsciousness": metric.unconsciousness if metric else None,
                "hypoglycemia": metric.hypoglycemia if metric else None,
                "high_fever": metric.high_fever if metric else None,
                "hypothermia": metric.hypothermia if metric else None,
                "severe_dehydration": metric.severe_dehydration if metric else None,
                "lower_respiratory_tract_infection": metric.lower_respiratory_tract_infection if metric else None,
                "severe_anemia": metric.severe_anemia if metric else None,
                "eye_signs_vit_a": metric.eye_signs_vit_a if metric else None,
                "skin_lesions": metric.skin_lesions if metric else None,
                "dietary_diversity_score": env.dietary_diversity_score if env else None,
                "breastfeeding": env.breastfeeding if env else None,
                "immunization_up_to_date": env.immunization_up_to_date if env else None,
                "recent_illness": env.recent_illness if env else None,
                "recent_illness_type": env.recent_illness_type if env else None,
                "water_source": household.water_source.name if household and household.water_source else None,
                "sanitation_type": (
                    household.sanitation_type.name if household and household.sanitation_type else None
                ),
                "floor_material": household.floor_material.name if household and household.floor_material else None,
                "wall_material": household.wall_material.name if household and household.wall_material else None,
                "roof_material": household.roof_material.name if household and household.roof_material else None,
                "household_income_proxy": household.household_income_proxy if household else None,
                "household_status_recorded_at": household.recorded_at if household else None,
                "household_status_age_days": (
                    (visit_date - household.recorded_at).days if household else None
                ),
            }
        )

    return pd.DataFrame(rows, columns=LONGFORM_COLUMNS)

from .models import Visit, Metric
import pygrowup
import logging
import datetime
import math


def calculate_age_at_date(patient, reference_date):
    """Return age at a reference date in days and months."""
    if not patient or not patient.dob or not reference_date:
        return {"days": None, "months": None}

    if isinstance(reference_date, datetime.datetime):
        reference_date = reference_date.date()

    if not isinstance(reference_date, datetime.date):
        return {"days": None, "months": None}

    dob_days = (reference_date - patient.dob).days
    age_months = dob_days / 30.4375 if dob_days is not None else None
    plus_days = dob_days - (math.floor(age_months) * 30.4375)
    return {"days": plus_days, "months": math.floor(age_months), "months_float": age_months, "dob_days": dob_days}


def calculate_zscore_for_metric(metric):
    """
    Calculates WAZ, HAZ, and WHZ for a given Metric instance using pygrowup.
    Updates the metric instance in place.
    """
    try:
        patient = metric.visit.patient
        dob = patient.dob
        visit_date = metric.visit.date.date()

        # Calculate age in months
        age_in_days = (visit_date - dob).days
        age_in_months = age_in_days / 30.4375

        gender = patient.gender.lower()
        if gender.startswith("m"):
            gender = "male"
        elif gender.startswith("f"):
            gender = "female"
        else:
            logging.error(f"Unknown gender: {patient.gender}")
            return

        # In pygrowup2 (jbaldivieso/pygrowup2), we use Observation instead of Calculator
        obs = pygrowup.Observation(sex=gender, age_in_months=age_in_months)

        # WAZ: Weight-for-age
        try:
            metric.wfaz = float(obs.wfa(metric.weight))
        except Exception as e:
            logging.warning(f"Error calculating WAZ: {e}")
            metric.wfaz = None

        # HAZ: Height-for-age
        try:
            # recumbent is the opposite of standing_or_upright
            recumbent = not metric.standing_or_upright if metric.standing_or_upright is not None else False
            metric.hfaz = float(obs.lhfa(metric.height, recumbent=recumbent))
        except Exception as e:
            logging.warning(f"Error calculating HAZ: {e}")
            metric.hfaz = None

        # WHZ: Weight-for-height
        try:
            metric.wfhz = float(obs.wfh(metric.weight, metric.height))
        except Exception as e:
            logging.warning(f"Error calculating WHZ: {e}")
            metric.wfhz = None

    except Exception as e:
        logging.error(f"Failed to calculate Z-scores: {e}")


def fetch_historical_metrics(person_id):
    """
    Fetches all visits and their associated metrics for a given person (child patient).
    Returns a dictionary with visit IDs as keys and a dictionary containing the visit date and metrics as values.
    """
    visits = Visit.objects.filter(patient=person_id)
    metrics = {}
    for v in visits:
        try:
            mets = Metric.objects.filter(visit=v)[0]
        except:
            mets = None
        metrics[v.id] = {"date": v.date, "metrics": mets}
    return metrics


def fetch_metrics_from_visits(visits):
    """
    Given a queryset of visits, fetches the associated metrics for each visit.
    Returns a list of dictionaries containing the visit and its associated metric or empty."""
    visits_metrics = []
    for visit in visits:
        try:
            metric = visit.metric
        except Metric.DoesNotExist:
            metric = None
        visits_metrics.append({"visit": visit, "metric": metric})
    return visits_metrics


def calculate_indexes():
    pass


def get_nutritional_status(latest_metric, previous_metric=None):
    """
    Evaluates nutritional status from WHO Z-scores, clinical signs, and trends.
    Returns a dictionary with status string, main badge CSS class, and list of badge dicts.

    FIXME: the ranges and the rule engine should be configurable.
    Range and criteria of metrics should not need just hard-coded values.
    """
    if not latest_metric:
        return {
            "status": "Sin datos",
            "badge_class": "secondary",
            "badges": [{"text": "Sin datos", "class": "secondary"}],
        }

    badges = []

    # Danger signs / Severe Acute Malnutrition with Edema
    if latest_metric.edema:
        badges.append({"text": "Desnutrición Aguda Severa (Edema)", "class": "danger"})
    elif latest_metric.wfhz is not None:
        if latest_metric.wfhz < -3:
            badges.append({"text": "Desnutrición Aguda Severa", "class": "danger"})
        elif latest_metric.wfhz < -2:
            badges.append({"text": "Desnutrición Aguda Moderada", "class": "warning"})
        elif latest_metric.wfhz > 3:
            badges.append({"text": "Obesidad", "class": "danger"})
        elif latest_metric.wfhz > 2:
            badges.append({"text": "Sobrepeso", "class": "warning"})

    # HAZ: Chronic malnutrition (stunting)
    if latest_metric.hfaz is not None:
        if latest_metric.hfaz < -3:
            badges.append({"text": "Desnutrición Crónica Severa", "class": "danger"})
        elif latest_metric.hfaz < -2:
            badges.append({"text": "Desnutrición Crónica", "class": "warning"})

    # WAZ: Underweight
    if latest_metric.wfaz is not None and not any(b["class"] in ("danger", "warning") for b in badges):
        if latest_metric.wfaz < -3:
            badges.append({"text": "Bajo Peso Severo", "class": "danger"})
        elif latest_metric.wfaz < -2:
            badges.append({"text": "Bajo Peso", "class": "warning"})

    # Weight loss alert compared to previous metric
    if (
        previous_metric
        and latest_metric.weight is not None
        and previous_metric.weight is not None
        and latest_metric.weight < previous_metric.weight
    ):
        badges.append({"text": "Alerta: Pérdida de Peso", "class": "danger"})

    if not badges:
        badges.append({"text": "Normal", "class": "success"})

    return {
        "status": ", ".join([b["text"] for b in badges]),
        "badge_class": badges[0]["class"],
        "badges": badges,
    }

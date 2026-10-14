from .models import Visit, Metric
import pygrowup
import logging
import datetime
import math

logger = logging.getLogger(__name__)

# WHO Child Growth Standards via pygrowup (full published tables):
# WFL 45–110 cm (recumbent), WFH 65–120 cm (standing). Combined WHZ: 45–120 cm.
WFL_HEIGHT_RANGE = (45.0, 110.0)
WFH_HEIGHT_RANGE = (65.0, 120.0)
WHZ_HEIGHT_RANGE = (WFL_HEIGHT_RANGE[0], WFH_HEIGHT_RANGE[1])


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


def _height_in_range(height, bounds):
    return height is not None and bounds[0] <= float(height) <= bounds[1]


def _whz_table_order(height, recumbent):
    """
    Return pygrowup WHZ methods to try, using the full WHO WFL∪WFH coverage.

    Prefer length (wfl) when recumbent or only WFL applies; prefer height (wfh)
    when standing or only WFH applies. In the 65–110 cm overlap, try the other
    table only if the preferred one fails.
    """
    can_wfl = _height_in_range(height, WFL_HEIGHT_RANGE)
    can_wfh = _height_in_range(height, WFH_HEIGHT_RANGE)
    prefer_wfl = recumbent or (height is not None and float(height) < WFH_HEIGHT_RANGE[0])

    ordered = []
    if prefer_wfl:
        if can_wfl:
            ordered.append("wfl")
        if can_wfh:
            ordered.append("wfh")
    else:
        if can_wfh:
            ordered.append("wfh")
        if can_wfl:
            ordered.append("wfl")
    return ordered


def _calculate_whz(obs, weight, height, recumbent):
    """Compute WHZ from WHO WFL/WFH tables; None when outside published ranges."""
    if weight is None or height is None:
        return None

    tables = _whz_table_order(height, recumbent)
    if not tables:
        logger.info(
            "WHZ skipped: height %s cm outside WHO tables (%.0f–%.0f cm)",
            height,
            WHZ_HEIGHT_RANGE[0],
            WHZ_HEIGHT_RANGE[1],
        )
        return None

    last_error = None
    for table in tables:
        method = getattr(obs, table)
        try:
            return float(method(weight, height))
        except (
            pygrowup.exceptions.AgeOutOfRangeError,
            pygrowup.exceptions.MeasurementOutOfRangeError,
            pygrowup.exceptions.ZScoreError,
        ) as e:
            last_error = e
        except Exception as e:
            last_error = e
            break

    if isinstance(
        last_error,
        (
            pygrowup.exceptions.AgeOutOfRangeError,
            pygrowup.exceptions.MeasurementOutOfRangeError,
            pygrowup.exceptions.ZScoreError,
        ),
    ):
        logger.info("WHZ not available: %s", last_error)
    elif last_error is not None:
        logger.warning("Error calculating WHZ: %s", last_error)
    return None


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
            logger.error("Unknown gender: %s", patient.gender)
            return

        # In pygrowup2 (jbaldivieso/pygrowup2), we use Observation instead of Calculator
        obs = pygrowup.Observation(sex=gender, age_in_months=age_in_months)

        # WAZ: Weight-for-age
        try:
            metric.wfaz = float(obs.wfa(metric.weight))
        except Exception as e:
            logger.warning("Error calculating WAZ: %s", e)
            metric.wfaz = None

        # recumbent is the opposite of standing_or_upright (None => standing)
        recumbent = not metric.standing_or_upright if metric.standing_or_upright is not None else False

        # HAZ: Height-for-age
        try:
            metric.hfaz = float(obs.lhfa(metric.height, recumbent=recumbent))
        except Exception as e:
            logger.warning("Error calculating HAZ: %s", e)
            metric.hfaz = None

        metric.wfhz = _calculate_whz(obs, metric.weight, metric.height, recumbent)

    except Exception:
        logger.exception("Failed to calculate Z-scores")


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

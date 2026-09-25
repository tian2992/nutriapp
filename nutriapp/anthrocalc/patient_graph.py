import io
import datetime
from decimal import Decimal
import django.http
from django.shortcuts import get_object_or_404
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from .models import Patient, Visit, Metric
from .who_reference import reference_band, normalize_sex
from .person_utils import calculate_age_at_date, fetch_metrics_from_visits


def render_growth_chart(
    series_list: list[dict],
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
) -> Figure:
    """
    Renders a growth chart from a generic list of series definitions.
    Decoupled from data sources (patient, group, or future fitted models).

    Each series item is a dict with:
    - 'label': str
    - 'xs': list[float]
    - 'ys': list[float]
    - 'style': dict (optional styling kwargs: color, linestyle, linewidth, marker, alpha, etc.)
    """
    fig = Figure(figsize=(8, 4.8), dpi=100)
    ax = fig.add_subplot(111)

    for item in series_list:
        xs = item.get("xs", [])
        ys = item.get("ys", [])
        if not xs or not ys:
            continue
        label = item.get("label", "")
        style = item.get("style", {})
        ax.plot(xs, ys, label=label, **style)

    if title:
        ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)

    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="best", fontsize=8, framealpha=0.85)
    fig.tight_layout()
    return fig


def render_chart_to_bytes(
    series_list: list[dict],
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
) -> bytes:
    """Renders growth chart and returns PNG image bytes."""
    fig = render_growth_chart(series_list, title=title, xlabel=xlabel, ylabel=ylabel)
    buf = io.BytesIO()
    canvas = FigureCanvas(fig)
    canvas.print_png(buf)
    return buf.getvalue()


def compute_patient_growth_series(
    patient: Patient,
    indicator: str = "hfa",
    visits_metrics: list[dict] | None = None,
) -> dict:
    """
    Computes WHO reference band series and patient raw measurement series.
    Supported indicators:
    - 'hfa' / 'haz' / 'talla': Height/Length-for-age (X=months, Y=cm)
    - 'wfa' / 'waz' / 'peso': Weight-for-age (X=months, Y=kg)
    - 'wfh' / 'wfhz' / 'whz' / 'wfl': Weight-for-height (transversal, X=cm, Y=kg)
    """
    ind = indicator.strip().lower()
    if ind in ("haz", "talla", "height", "lfa", "lhfa"):
        ind = "hfa"
    elif ind in ("waz", "peso", "weight"):
        ind = "wfa"
    elif ind in ("whz", "wfhz", "wfl"):
        ind = "wfh"

    sex = normalize_sex(patient.gender) if patient.gender else "male"

    # Fetch visits & metrics if not supplied
    if visits_metrics is None:
        visits = Visit.objects.filter(patient=patient).order_by("date").prefetch_related("metric")
        visits_metrics = fetch_metrics_from_visits(visits)

    patient_points = []
    is_recumbent_overall = False

    for item in visits_metrics:
        visit = item.get("visit")
        metric = item.get("metric")
        if not visit or not metric:
            continue

        vdate = visit.date.date() if isinstance(visit.date, datetime.datetime) else visit.date
        age_days = (vdate - patient.dob).days if patient.dob and vdate else None
        age_months = age_days / 30.4375 if age_days is not None else None

        if ind == "hfa" and metric.height is not None and age_months is not None:
            patient_points.append((float(age_months), float(metric.height)))
        elif ind == "wfa" and metric.weight is not None and age_months is not None:
            patient_points.append((float(age_months), float(metric.weight)))
        elif ind == "wfh" and metric.height is not None and metric.weight is not None:
            patient_points.append((float(metric.height), float(metric.weight)))
            if metric.standing_or_upright is False:
                is_recumbent_overall = True

    # Determine reference indicator and point grid
    if ind in ("hfa", "wfa"):
        max_patient_age = max([pt[0] for pt in patient_points], default=0.0)
        max_age = max(60, int(math_ceil(max_patient_age)) + 2)
        ref_points = list(range(0, max_age + 1))
        ref_indicator = ind
        xlabel = "Edad (meses)"
        if ind == "hfa":
            ylabel = "Talla / Longitud (cm)"
            title = f"Talla para la Edad (HAZ) - {patient.name}"
        else:
            ylabel = "Peso (kg)"
            title = f"Peso para la Edad (WAZ) - {patient.name}"
    else:
        # Cross-sectional WHZ
        ref_indicator = "wfl" if is_recumbent_overall else "wfh"
        if ref_indicator == "wfl":
            ref_points = [round(45.0 + i * 1.0, 1) for i in range(66)]  # 45 to 110 cm
        else:
            ref_points = [round(65.0 + i * 1.0, 1) for i in range(56)]  # 65 to 120 cm
        xlabel = "Talla / Longitud (cm)"
        ylabel = "Peso (kg)"
        title = f"Peso para la Talla (WHZ) - {patient.name}"

    bands = reference_band(ref_indicator, sex, ref_points)
    xs = [b["x"] for b in bands]

    series = [
        {
            "label": "+2 SD",
            "xs": xs,
            "ys": [b["+2SD"] for b in bands],
            "style": {"color": "#d9534f", "linestyle": "--", "linewidth": 1.2, "alpha": 0.8},
        },
        {
            "label": "+1 SD",
            "xs": xs,
            "ys": [b["+1SD"] for b in bands],
            "style": {"color": "#f0ad4e", "linestyle": "--", "linewidth": 1.2, "alpha": 0.8},
        },
        {
            "label": "0 (Mediana OMS)",
            "xs": xs,
            "ys": [b["0"] for b in bands],
            "style": {"color": "#28a745", "linestyle": "-", "linewidth": 1.8},
        },
        {
            "label": "-1 SD",
            "xs": xs,
            "ys": [b["-1SD"] for b in bands],
            "style": {"color": "#f0ad4e", "linestyle": "--", "linewidth": 1.2, "alpha": 0.8},
        },
        {
            "label": "-2 SD",
            "xs": xs,
            "ys": [b["-2SD"] for b in bands],
            "style": {"color": "#d9534f", "linestyle": "--", "linewidth": 1.2, "alpha": 0.8},
        },
    ]

    # Add patient points series
    if patient_points:
        # Sort by X
        patient_points.sort(key=lambda p: p[0])
        p_xs = [pt[0] for pt in patient_points]
        p_ys = [pt[1] for pt in patient_points]
        series.append({
            "label": f"Mediciones ({patient.name})",
            "xs": p_xs,
            "ys": p_ys,
            "style": {
                "color": "#0056b3",
                "linestyle": "-",
                "linewidth": 2.0,
                "marker": "o",
                "markersize": 6,
            },
        })

    return {
        "title": title,
        "xlabel": xlabel,
        "ylabel": ylabel,
        "series": series,
    }


def compute_group_growth_series(
    patients,
    indicator: str = "hfa",
    group_name: str = "Grupo",
    sex: str = "male",
) -> dict:
    """
    Stub for future Phase 2 group visualization mode.
    Allows aggregating or plotting multiple child trajectories alongside WHO bands.
    """
    ind = indicator.strip().lower()
    if ind in ("haz", "talla", "height", "lfa", "lhfa"):
        ind = "hfa"
    elif ind in ("waz", "peso", "weight"):
        ind = "wfa"
    elif ind in ("whz", "wfhz", "wfl"):
        ind = "wfh"

    if ind in ("hfa", "wfa"):
        ref_points = list(range(0, 61))
        xlabel = "Edad (meses)"
        ylabel = "Talla / Longitud (cm)" if ind == "hfa" else "Peso (kg)"
    else:
        ref_points = [round(65.0 + i * 1.0, 1) for i in range(56)]
        xlabel = "Talla / Longitud (cm)"
        ylabel = "Peso (kg)"

    bands = reference_band(ind, sex, ref_points)
    xs = [b["x"] for b in bands]

    series = [
        {
            "label": "+2 SD",
            "xs": xs,
            "ys": [b["+2SD"] for b in bands],
            "style": {"color": "#d9534f", "linestyle": "--", "linewidth": 1.0, "alpha": 0.7},
        },
        {
            "label": "0 (Mediana OMS)",
            "xs": xs,
            "ys": [b["0"] for b in bands],
            "style": {"color": "#28a745", "linestyle": "-", "linewidth": 1.5},
        },
        {
            "label": "-2 SD",
            "xs": xs,
            "ys": [b["-2SD"] for b in bands],
            "style": {"color": "#d9534f", "linestyle": "--", "linewidth": 1.0, "alpha": 0.7},
        },
    ]

    for p in patients:
        p_res = compute_patient_growth_series(p, indicator=ind)
        for s in p_res.get("series", []):
            if s.get("label", "").startswith("Mediciones"):
                s["label"] = p.name or f"Paciente {p.id}"
                s["style"] = {"linestyle": "-", "linewidth": 1.2, "marker": "o", "markersize": 4}
                series.append(s)

    return {
        "title": f"Crecimiento Grupal - {group_name}",
        "xlabel": xlabel,
        "ylabel": ylabel,
        "series": series,
    }


def math_ceil(val: float) -> int:
    import math
    return math.ceil(val)


def graph_for_person(request):
    """
    HTTP view returning personal growth chart PNG for a given person/patient.
    Accepts GET parameters:
    - person_id or patient_id (int)
    - indicator (str: 'hfa', 'wfa', 'wfh' / 'whz', default 'hfa')
    """
    person_id = request.GET.get("person_id") or request.GET.get("patient_id")
    if not person_id:
        return django.http.HttpResponseBadRequest("person_id parameter is required")

    try:
        person_id = int(person_id)
    except ValueError:
        return django.http.HttpResponseBadRequest("Invalid person_id")

    patient = get_object_or_404(Patient, id=person_id)
    indicator = request.GET.get("indicator", "hfa")

    chart_data = compute_patient_growth_series(patient, indicator=indicator)
    image_bytes = render_chart_to_bytes(
        series_list=chart_data["series"],
        title=chart_data["title"],
        xlabel=chart_data["xlabel"],
        ylabel=chart_data["ylabel"],
    )

    return django.http.HttpResponse(image_bytes, content_type="image/png")


def simple(request):
    """Placeholder simple chart for testing."""
    buf = io.BytesIO()
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1, 2], [0, 1, 4], "-")
    canvas = FigureCanvas(fig)
    canvas.print_png(buf)
    return django.http.HttpResponse(buf.getvalue(), content_type="image/png")

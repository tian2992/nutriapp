import django.http
from django.shortcuts import get_object_or_404

from .models import Patient
from .patient_graph import (
    compute_patient_growth_series,
    render_blank_chart_to_bytes,
    render_chart_to_bytes,
)


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
    """HTTP view returning a blank chart PNG."""
    image_bytes = render_blank_chart_to_bytes()
    return django.http.HttpResponse(image_bytes, content_type="image/png")

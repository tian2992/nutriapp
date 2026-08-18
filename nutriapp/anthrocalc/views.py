import csv
import datetime
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.manager import BaseManager
from django.forms import formset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import context
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.views import View
from django.views.generic import ListView, TemplateView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .forms import (
    CommunityForm,
    MassMeasurementHeaderForm,
    MassMeasurementRowForm,
    MetricForm,
    PatientForm,
)
from .models import *
from .person_utils import (
    calculate_age_at_date,
    fetch_historical_metrics,
    fetch_metrics_from_visits,
    get_nutritional_status,
)


@method_decorator(login_required, name="dispatch")
class ExportableListView(ListView):
    template_name = "anthrocalc/generic_list.html"
    table_fields = []  # List of (field_name, label) tuples
    title = ""
    new_url_name = ""
    edit_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fields"] = [f[0] for f in self.table_fields]
        context["labels"] = [f[1] for f in self.table_fields]
        context["title"] = self.title
        if self.new_url_name:
            context["new_url"] = reverse(self.new_url_name)
        context["edit_url_name"] = self.edit_url_name
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            return self.export_csv()
        return super().get(request, *args, **kwargs)

    def export_csv(self):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{self.model.__name__.lower()}_list.csv"'

        writer = csv.writer(response)
        writer.writerow([f[1] for f in self.table_fields])

        for obj in self.get_queryset():
            row = []
            for field, label in self.table_fields:
                val = obj
                for part in field.replace("__", ".").split("."):
                    val = getattr(val, part, "")
                if callable(val):
                    try:
                        val = val()
                    except:
                        pass
                row.append(val)
            writer.writerow(row)
        return response


# Views for Patients


class PatientList(ExportableListView):
    model = Patient
    template_name = "anthrocalc/patient_list.html"
    title = "Niños registrados"
    table_fields = [
        ("id", "ID"),
        ("code", "Código"),
        ("name", "Nombre"),
        ("dob", "Fecha de Nacimiento"),
        ("family__community__name", "Comunidad"),
        ("family__responsible_name", "Familia"),
    ]
    new_url_name = "patients:new"
    edit_url_name = "patients:edit"

    def get_queryset(self):
        qs = super().get_queryset()
        community_id = self.request.GET.get("community")
        if community_id:
            qs = qs.filter(family__community_id=community_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["communities"] = Community.objects.all()
        context["selected_community"] = self.request.GET.get("community", "")
        return context


@method_decorator(login_required, name="dispatch")
class PatientDetail(DetailView):
    model = Patient

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visits: BaseManager[Visit] = (
            Visit.objects.filter(patient=self.object).order_by("date").prefetch_related("metric")
        )
        context["visits"] = visits
        visits_metrics = fetch_metrics_from_visits(visits)

        for item in visits_metrics:
            age = calculate_age_at_date(self.object, item["visit"].date)
            item["age_days"] = age["days"]
            item["age_months"] = age["months"]

        context["visits_metrics"] = visits_metrics
        return context


class PatientCreation(CreateView):
    model = Patient
    form_class = PatientForm
    success_url = reverse_lazy("patients:list")

    def get_initial(self):
        initial = super().get_initial()
        if "community" in self.request.GET:
            initial["community"] = self.request.GET["community"]
        return initial


class PatientUpdate(UpdateView):
    model = Patient
    form_class = PatientForm
    success_url = reverse_lazy("patients:list")


class PatientDelete(DeleteView):
    model = Patient
    success_url = reverse_lazy("patients:list")


# Views for Visits


class VisitList(ExportableListView):
    model = Visit
    title = "Listado de Visitas"
    table_fields = [
        ("id", "ID"),
        ("patient__name", "Niño"),
        ("patient__family__community__name", "Comunidad"),
        ("date", "Fecha"),
        ("notes", "Notas"),
    ]
    new_url_name = "visits:new"
    edit_url_name = "visits:edit"

    ordering = ["-date"]

    def get_queryset(self):
        qs = super().get_queryset()
        community_id = self.request.GET.get("community")
        if community_id:
            qs = qs.filter(patient__family__community_id=community_id)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["communities"] = Community.objects.all()
        context["selected_community"] = self.request.GET.get("community", "")
        return context


@method_decorator(login_required, name="dispatch")
class VisitDetail(DetailView):
    model = Visit

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["metrics"] = Metric.objects.filter(visit=self.object.id)
        context["env_metrics"] = EnvironmentMetric.objects.filter(visit=self.object.id)
        try:
            context["household_status"] = HouseholdStatus.objects.get(family=self.object.patient.family)
        except HouseholdStatus.DoesNotExist:
            context["household_status"] = None
        return context


class VisitCreation(CreateView):
    model = Visit
    metric = Metric
    success_url = reverse_lazy("visits:list")  ## TODO: redirect to new metric
    # success_url = reverse_lazy('metrics:newvm')
    # +"?visit={{visit.id}}"
    # ", args=metric.id)
    fields = "__all__"

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.id,))

    def get_initial(self):
        initial = super().get_initial()
        if "patient" in self.request.GET:
            initial["patient"] = self.request.GET["patient"]
        return initial


class VisitUpdate(UpdateView):
    model = Visit
    success_url = reverse_lazy("visits:list")
    fields = ["patient", "date"]


class VisitDelete(DeleteView):
    model = Visit
    success_url = reverse_lazy("visits:list")


# Views for Metrics


class MetricList(ExportableListView):
    model = Metric
    template_name = "anthrocalc/metric_list.html"
    title = "Listado de Métricas"
    table_fields = [
        ("id", "ID"),
        ("visit__patient__name", "Niño"),
        ("visit__date", "Fecha de Visita"),
        ("weight", "Peso (kg)"),
        ("height", "Altura (cm)"),
    ]
    new_url_name = "metrics:new"
    edit_url_name = "metrics:edit"


@method_decorator(login_required, name="dispatch")
class MetricDetail(DetailView):
    model = Metric
    model = Metric


class MetricCreation(CreateView):
    model = Metric
    form_class = MetricForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "visit" in self.request.GET:
            try:
                context["visit"] = Visit.objects.get(id=self.request.GET["visit"])
            except Visit.DoesNotExist:
                pass
        if "patient" in self.request.GET:
            try:
                context["patient"] = Patient.objects.get(id=self.request.GET["patient"])
            except Patient.DoesNotExist:
                pass
        return context

    def get_initial(self):
        initial = super().get_initial()
        if "visit" in self.request.GET:
            visit_id = self.request.GET["visit"]
            initial["visit"] = visit_id
        if "patient" in self.request.GET:
            initial["patient"] = self.request.GET["patient"]
        return initial

    def form_valid(self, form):
        if not form.cleaned_data.get("visit"):
            patient = form.cleaned_data.get("patient")
            visit = Visit.objects.create(patient=patient)
            form.instance.visit = visit
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.visit.id,))

    # fields = ['visit.patient', 'weight', 'height']


class MetricUpdate(UpdateView):
    model = Metric
    form_class = MetricForm

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.visit.id,))


class MetricDelete(DeleteView):
    model = Metric
    success_url = reverse_lazy("metrics:list")


class EnvironmentMetricCreation(CreateView):
    model = EnvironmentMetric
    fields = [
        "visit",
        "dietary_diversity_score",
        "breastfeeding",
        "immunization_up_to_date",
        "recent_illness",
        "recent_illness_type",
        "notes",
    ]

    def get_initial(self):
        initial = super().get_initial()
        if "visit" in self.request.GET:
            initial["visit"] = self.request.GET["visit"]
        return initial

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.visit.id,))


class EnvironmentMetricUpdate(UpdateView):
    model = EnvironmentMetric
    fields = [
        "dietary_diversity_score",
        "breastfeeding",
        "immunization_up_to_date",
        "recent_illness",
        "recent_illness_type",
        "notes",
    ]

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.visit.id,))


class HouseholdStatusCreation(CreateView):
    model = HouseholdStatus
    fields = [
        "family",
        "water_source",
        "sanitation_type",
        "floor_material",
        "wall_material",
        "roof_material",
        "household_income_proxy",
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        family_id = self.request.GET.get("family")
        context["family"] = None
        if family_id:
            try:
                context["family"] = Family.objects.get(id=family_id)
            except (Family.DoesNotExist, ValueError):
                pass
        return context

    def get_initial(self):
        initial = super().get_initial()
        if "family" in self.request.GET:
            initial["family"] = self.request.GET["family"]
        return initial

    def get_success_url(self):
        # We don't have a direct way back to visit from family easily here without extra context
        # but usually it's created from patient detail or visit detail
        if "next" in self.request.GET:
            return self.request.GET["next"]
        return reverse("patients:list")


class HouseholdStatusUpdate(UpdateView):
    model = HouseholdStatus
    fields = [
        "water_source",
        "sanitation_type",
        "floor_material",
        "wall_material",
        "roof_material",
        "household_income_proxy",
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["family"] = self.object.family
        return context

    def get_success_url(self):
        if "next" in self.request.GET:
            return self.request.GET["next"]
        return reverse("patients:list")


class LandingPageView(TemplateView):
    template_name = "anthrocalc/landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contact_email"] = "code@sebastianoliva.com"
        context["patient_count"] = Patient.objects.count()
        context["visit_count"] = Visit.objects.count()
        context["metric_count"] = Metric.objects.count()
        context["community_count"] = Community.objects.count()
        return context


# Views for Communities


class CommunityList(ExportableListView):
    model = Community
    template_name = "anthrocalc/community_list.html"
    title = "Listado de Comunidades"
    table_fields = [
        ("id", "ID"),
        ("name", "Nombre"),
        ("municipality", "Municipio"),
        ("department", "Departamento"),
        ("contact_person", "Encargado / Promotor"),
    ]
    new_url_name = "communities:new"
    edit_url_name = "communities:edit"


@method_decorator(login_required, name="dispatch")
class CommunityDetail(DetailView):
    model = Community
    template_name = "anthrocalc/community_roster.html"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.GET.get("export") == "csv":
            return self.export_roster_csv()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        community = self.object
        patients = (
            Patient.objects.filter(family__community=community)
            .select_related("family")
            .order_by("name")
        )

        roster = []
        today = now().date()
        for patient in patients:
            visits = (
                Visit.objects.filter(patient=patient)
                .order_by("date")
                .select_related("metric")
            )
            age_info = calculate_age_at_date(patient, today)

            visits_metrics = []
            for v in visits:
                try:
                    m = v.metric
                except Metric.DoesNotExist:
                    m = None
                if m:
                    visits_metrics.append((v, m))

            prev_visit, prev_metric = (None, None)
            latest_visit, latest_metric = (None, None)

            if len(visits_metrics) >= 2:
                prev_visit, prev_metric = visits_metrics[-2]
                latest_visit, latest_metric = visits_metrics[-1]
            elif len(visits_metrics) == 1:
                latest_visit, latest_metric = visits_metrics[-1]

            status_info = get_nutritional_status(latest_metric, prev_metric)

            roster.append({
                "patient": patient,
                "age_months": age_info.get("months"),
                "prev_visit": prev_visit,
                "prev_metric": prev_metric,
                "latest_visit": latest_visit,
                "latest_metric": latest_metric,
                "status_info": status_info,
            })

        context["roster"] = roster
        context["total_children"] = patients.count()
        last_mv = MultipleVisit.objects.filter(community=community).order_by("-date").first()
        context["last_measurement_date"] = last_mv.date if last_mv else None
        context["multiple_visits"] = MultipleVisit.objects.filter(community=community).order_by("-date")[:10]
        return context

    def export_roster_csv(self):
        response = HttpResponse(content_type="text/csv")
        clean_name = self.object.name.lower().replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="comunidad_{clean_name}_listado.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Código",
            "Nombre del Niño",
            "Tutor / Madre",
            "Fecha de Nacimiento",
            "Edad (meses)",
            "Sexo",
            "Fecha Medición Anterior",
            "Peso Anterior (kg)",
            "Altura Anterior (cm)",
            "Fecha Última Medición",
            "Peso Última Medición (kg)",
            "Altura Última Medición (cm)",
            "WHZ",
            "WAZ",
            "HAZ",
            "Estado Nutricional",
        ])

        today = now().date()
        patients = (
            Patient.objects.filter(family__community=self.object)
            .select_related("family")
            .order_by("name")
        )
        for patient in patients:
            visits = (
                Visit.objects.filter(patient=patient)
                .order_by("date")
                .select_related("metric")
            )
            age_info = calculate_age_at_date(patient, today)
            visits_metrics = []
            for v in visits:
                try:
                    m = v.metric
                except Metric.DoesNotExist:
                    m = None
                if m:
                    visits_metrics.append((v, m))

            prev_visit, prev_metric = (None, None)
            latest_visit, latest_metric = (None, None)
            if len(visits_metrics) >= 2:
                prev_visit, prev_metric = visits_metrics[-2]
                latest_visit, latest_metric = visits_metrics[-1]
            elif len(visits_metrics) == 1:
                latest_visit, latest_metric = visits_metrics[-1]
            status_info = get_nutritional_status(latest_metric, prev_metric)

            writer.writerow([
                patient.code,
                patient.name,
                patient.family.responsible_name if patient.family else "",
                patient.dob.strftime("%Y-%m-%d") if patient.dob else "",
                age_info.get("months", ""),
                patient.gender,
                prev_visit.date.strftime("%Y-%m-%d") if prev_visit else "",
                prev_metric.weight if prev_metric else "",
                prev_metric.height if prev_metric else "",
                latest_visit.date.strftime("%Y-%m-%d") if latest_visit else "",
                latest_metric.weight if latest_metric else "",
                latest_metric.height if latest_metric else "",
                latest_metric.wfhz if latest_metric and latest_metric.wfhz is not None else "",
                latest_metric.wfaz if latest_metric and latest_metric.wfaz is not None else "",
                latest_metric.hfaz if latest_metric and latest_metric.hfaz is not None else "",
                status_info.get("status", ""),
            ])
        return response


class CommunityCreation(CreateView):
    model = Community
    form_class = CommunityForm
    template_name = "anthrocalc/community_form.html"
    success_url = reverse_lazy("communities:list")


class CommunityUpdate(UpdateView):
    model = Community
    form_class = CommunityForm
    template_name = "anthrocalc/community_form.html"
    success_url = reverse_lazy("communities:list")


class CommunityDelete(DeleteView):
    model = Community
    template_name = "anthrocalc/community_confirm_delete.html"
    success_url = reverse_lazy("communities:list")


@method_decorator(login_required, name="dispatch")
class CommunityMassVisit(View):
    template_name = "anthrocalc/community_mass_visit.html"

    def get_patients_data(self, community):
        patients = (
            Patient.objects.filter(family__community=community)
            .select_related("family")
            .order_by("name")
        )
        data = []
        today = now().date()
        for p in patients:
            age_info = calculate_age_at_date(p, today)
            last_visit = (
                Visit.objects.filter(patient=p)
                .order_by("-date")
                .select_related("metric")
                .first()
            )
            last_metric = None
            if last_visit:
                try:
                    last_metric = last_visit.metric
                except Metric.DoesNotExist:
                    last_metric = None
            data.append({
                "patient": p,
                "age_months": age_info.get("months"),
                "prev_visit": last_visit,
                "prev_metric": last_metric,
            })
        return data

    def get(self, request, pk):
        community = get_object_or_404(Community, pk=pk)
        patients_data = self.get_patients_data(community)

        header_form = MassMeasurementHeaderForm(initial={
            "date": now().date(),
            "responsible_name": (
                request.user.get_full_name() or request.user.username
                if request.user.is_authenticated else ""
            ),
        })

        MassFormSet = formset_factory(MassMeasurementRowForm, extra=0)
        initial_rows = [{"patient_id": item["patient"].id} for item in patients_data]
        formset = MassFormSet(initial=initial_rows, prefix="rows")

        rows = list(zip(formset.forms, patients_data))

        return render(
            request,
            self.template_name,
            {
                "community": community,
                "header_form": header_form,
                "formset": formset,
                "rows": rows,
            },
        )

    def post(self, request, pk):
        community = get_object_or_404(Community, pk=pk)
        patients_data = self.get_patients_data(community)

        header_form = MassMeasurementHeaderForm(request.POST)
        MassFormSet = formset_factory(MassMeasurementRowForm, extra=0)
        formset = MassFormSet(request.POST, prefix="rows")

        if header_form.is_valid() and formset.is_valid():
            jornada_date = header_form.cleaned_data["date"]
            responsible_name = header_form.cleaned_data.get("responsible_name", "")
            notes = header_form.cleaned_data.get("notes", "")

            jornada_datetime = datetime.datetime.combine(jornada_date, datetime.time(12, 0))
            if settings.USE_TZ:
                from django.utils.timezone import get_current_timezone, make_aware
                try:
                    jornada_datetime = make_aware(jornada_datetime, get_current_timezone())
                except Exception:
                    pass

            created_count = 0
            with transaction.atomic():
                multiple_visit = MultipleVisit.objects.create(
                    community=community,
                    date=jornada_datetime,
                    responsible_name=responsible_name,
                    notes=notes,
                )

                for form in formset.forms:
                    if form.has_data():
                        patient_id = form.cleaned_data["patient_id"]
                        patient = Patient.objects.get(id=patient_id)
                        row_notes = form.cleaned_data.get("notes", "")
                        weight = form.cleaned_data["weight"]
                        height = form.cleaned_data["height"]
                        standing_val = form.cleaned_data.get("standing_or_upright")
                        standing_or_upright = (
                            True if standing_val == "True" else False if standing_val == "False" else None
                        )
                        muac = form.cleaned_data.get("muac")
                        edema = form.cleaned_data.get("edema", False)

                        visit = Visit.objects.create(
                            patient=patient,
                            date=jornada_datetime,
                            multiple_visit=multiple_visit,
                            notes=row_notes if row_notes else None,
                        )
                        metric = Metric(
                            visit=visit,
                            weight=weight,
                            height=height,
                            standing_or_upright=standing_or_upright,
                            muac=muac,
                            edema=edema,
                        )
                        metric.save()
                        created_count += 1

            if created_count > 0:
                messages.success(
                    request,
                    f"Se registraron exitosamente {created_count} mediciones en la jornada para {community.name}.",
                )
            else:
                messages.info(
                    request,
                    f"Se creó la jornada para {community.name}, pero no se ingresaron mediciones.",
                )
            return redirect(reverse("communities:detail", args=[community.id]))

        rows = list(zip(formset.forms, patients_data))
        return render(
            request,
            self.template_name,
            {
                "community": community,
                "header_form": header_form,
                "formset": formset,
                "rows": rows,
            },
        )

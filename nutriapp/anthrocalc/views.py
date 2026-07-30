import csv

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models.manager import BaseManager
from django.http import Http404, HttpResponse
from django.template import context
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from .forms import HouseholdStatusForm, MetricForm, PatientForm, VisitForm
from .models import *
from .person_utils import (
    calculate_age_at_date,
    fetch_historical_metrics,
    fetch_metrics_from_visits,
)


class FamilyAccessMixin:
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.is_superuser or user.is_staff:
            return queryset

        if queryset.model is Family:
            return queryset.filter(allowed_users=user)
        if queryset.model is Patient:
            return queryset.filter(family__allowed_users=user)
        if queryset.model is Visit:
            return queryset.filter(patient__family__allowed_users=user)
        if queryset.model is Metric:
            return queryset.filter(visit__patient__family__allowed_users=user)
        if queryset.model is HouseholdStatus:
            return queryset.filter(family__allowed_users=user)
        if queryset.model is EnvironmentMetric:
            return queryset.filter(visit__patient__family__allowed_users=user)
        return queryset

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)
        try:
            return queryset.get(pk=pk)
        except queryset.model.DoesNotExist:
            try:
                existing_obj = self.model.objects.get(pk=pk)
            except self.model.DoesNotExist as exc:
                raise Http404 from exc
            if self.can_access_object(existing_obj):
                raise Http404
            raise PermissionDenied

    def can_access_object(self, obj):
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return True
        if isinstance(obj, Family):
            return obj.allowed_users.filter(pk=user.pk).exists()
        if isinstance(obj, Patient):
            return bool(obj.family and obj.family.allowed_users.filter(pk=user.pk).exists())
        if isinstance(obj, Visit):
            return bool(obj.patient and obj.patient.family and obj.patient.family.allowed_users.filter(pk=user.pk).exists())
        if isinstance(obj, Metric):
            return bool(
                obj.visit
                and obj.visit.patient
                and obj.visit.patient.family
                and obj.visit.patient.family.allowed_users.filter(pk=user.pk).exists()
            )
        if isinstance(obj, HouseholdStatus):
            return obj.family.allowed_users.filter(pk=user.pk).exists()
        return False


class ExportableListView(FamilyAccessMixin, LoginRequiredMixin, ListView):
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
        ("family__responsible_name", "Familia"),
    ]
    new_url_name = "patients:new"
    edit_url_name = "patients:edit"


class PatientDetail(FamilyAccessMixin, LoginRequiredMixin, DetailView):
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


class PatientCreation(FamilyAccessMixin, LoginRequiredMixin, CreateView):
    model = Patient
    form_class = PatientForm
    success_url = reverse_lazy("patients:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PatientUpdate(FamilyAccessMixin, LoginRequiredMixin, UpdateView):
    model = Patient
    form_class = PatientForm
    success_url = reverse_lazy("patients:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PatientDelete(FamilyAccessMixin, LoginRequiredMixin, DeleteView):
    model = Patient
    success_url = reverse_lazy("patients:list")


# Views for Visits


class VisitList(ExportableListView):
    model = Visit
    title = "Listado de Visitas"
    table_fields = [
        ("id", "ID"),
        ("patient__name", "Niño"),
        ("date", "Fecha"),
        ("notes", "Notas"),
    ]
    new_url_name = "visits:new"
    edit_url_name = "visits:edit"

    ordering = ["-date"]


class VisitDetail(FamilyAccessMixin, LoginRequiredMixin, DetailView):
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


class VisitCreation(FamilyAccessMixin, LoginRequiredMixin, CreateView):
    model = Visit
    metric = Metric
    success_url = reverse_lazy("visits:list")  ## TODO: redirect to new metric
    # success_url = reverse_lazy('metrics:newvm')
    # +"?visit={{visit.id}}"
    # ", args=metric.id)
    form_class = VisitForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.id,))

    def get_initial(self):
        initial = super().get_initial()
        if "patient" in self.request.GET:
            initial["patient"] = self.request.GET["patient"]
        return initial


class VisitUpdate(FamilyAccessMixin, LoginRequiredMixin, UpdateView):
    model = Visit
    success_url = reverse_lazy("visits:list")
    form_class = VisitForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class VisitDelete(FamilyAccessMixin, LoginRequiredMixin, DeleteView):
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


class MetricDetail(FamilyAccessMixin, LoginRequiredMixin, DetailView):
    model = Metric


class MetricCreation(FamilyAccessMixin, LoginRequiredMixin, CreateView):
    model = Metric
    form_class = MetricForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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


class MetricUpdate(FamilyAccessMixin, LoginRequiredMixin, UpdateView):
    model = Metric
    form_class = MetricForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("visits:detail", args=(self.object.visit.id,))


class MetricDelete(FamilyAccessMixin, LoginRequiredMixin, DeleteView):
    model = Metric
    success_url = reverse_lazy("metrics:list")


class EnvironmentMetricCreation(FamilyAccessMixin, LoginRequiredMixin, CreateView):
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


class EnvironmentMetricUpdate(FamilyAccessMixin, LoginRequiredMixin, UpdateView):
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


class HouseholdStatusCreation(FamilyAccessMixin, LoginRequiredMixin, CreateView):
    model = HouseholdStatus
    form_class = HouseholdStatusForm

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

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

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


class HouseholdStatusUpdate(FamilyAccessMixin, LoginRequiredMixin, UpdateView):
    model = HouseholdStatus
    form_class = HouseholdStatusForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["family"] = self.object.family
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        if "next" in self.request.GET:
            return self.request.GET["next"]
        return reverse("patients:list")

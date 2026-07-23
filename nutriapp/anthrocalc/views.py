import csv
from django.http import HttpResponse
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView
)
from .models import *
from .forms import MetricForm

from .person_utils import fetch_historical_metrics


class ExportableListView(ListView):
    template_name = 'anthrocalc/generic_list.html'
    table_fields = []  # List of (field_name, label) tuples
    title = ""
    new_url_name = ""
    edit_url_name = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = [f[0] for f in self.table_fields]
        context['labels'] = [f[1] for f in self.table_fields]
        context['title'] = self.title
        if self.new_url_name:
            context['new_url'] = reverse(self.new_url_name)
        context['edit_url_name'] = self.edit_url_name
        return context

    def get(self, request, *args, **kwargs):
        if request.GET.get('export') == 'csv':
            return self.export_csv()
        return super().get(request, *args, **kwargs)

    def export_csv(self):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.model.__name__.lower()}_list.csv"'

        writer = csv.writer(response)
        writer.writerow([f[1] for f in self.table_fields])

        for obj in self.get_queryset():
            row = []
            for field, label in self.table_fields:
                val = obj
                for part in field.replace('__', '.').split('.'):
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
    title = "Niños registrados"
    table_fields = [
        ('id', 'ID'),
        ('code', 'Código'),
        ('name', 'Nombre'),
        ('dob', 'Fecha de Nacimiento'),
        ('family__responsible_name', 'Familia'),
    ]
    new_url_name = 'patients:new'
    edit_url_name = 'patients:edit'


class PatientDetail(DetailView):
    model = Patient

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visits = Visit.objects.filter(patient=self.object.id)
        context['visits'] = visits
        context['metrics_dict'] = fetch_historical_metrics(self.object.id)
        return context


class PatientCreation(CreateView):
    model = Patient
    success_url = reverse_lazy('patients:list')
    fields = ['code', 'name', 'gender', 'dob', 'family', 'mother_name', 'birth_weight', 'birth_length', 'maternal_education']


class PatientUpdate(UpdateView):
    model = Patient
    success_url = reverse_lazy('patients:list')
    fields = ['code', 'name', 'gender', 'dob', 'family', 'mother_name', 'birth_weight', 'birth_length', 'maternal_education']


class PatientDelete(DeleteView):
    model = Patient
    success_url = reverse_lazy('patients:list')


# Views for Visits


class VisitList(ExportableListView):
    model = Visit
    title = "Listado de Visitas"
    table_fields = [
        ('id', 'ID'),
        ('patient__name', 'Niño'),
        ('date', 'Fecha'),
        ('notes', 'Notas'),
    ]
    new_url_name = 'visits:new'
    edit_url_name = 'visits:edit'

    ordering = ['-date']

class VisitDetail(DetailView):
    model = Visit

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['metrics'] = Metric.objects.filter(visit=self.object.id)
        context['env_metrics'] = EnvironmentMetric.objects.filter(visit=self.object.id)
        try:
            context['household_status'] = HouseholdStatus.objects.get(family=self.object.patient.family)
        except HouseholdStatus.DoesNotExist:
            context['household_status'] = None
        return context


class VisitCreation(CreateView):
    model = Visit
    metric = Metric
    success_url = reverse_lazy('visits:list') ## TODO: redirect to new metric
    #success_url = reverse_lazy('metrics:newvm')
    #+"?visit={{visit.id}}"
    # ", args=metric.id)
    fields = '__all__'

    def get_success_url(self):
        return reverse('visits:detail',args=(self.object.id,))

    def get_initial(self):
        initial = super().get_initial()
        if "patient" in self.request.GET:
            initial['patient'] = self.request.GET["patient"]
        return initial


class VisitUpdate(UpdateView):
    model = Visit
    success_url = reverse_lazy('visits:list')
    fields = ['patient', 'date']


class VisitDelete(DeleteView):
    model = Visit
    success_url = reverse_lazy('visits:list')


# Views for Metrics


class MetricList(ExportableListView):
    model = Metric
    title = "Listado de Métricas"
    table_fields = [
        ('id', 'ID'),
        ('visit__patient__name', 'Niño'),
        ('visit__date', 'Fecha de Visita'),
        ('weight', 'Peso (kg)'),
        ('height', 'Altura (cm)'),
    ]
    new_url_name = 'metrics:new'
    edit_url_name = 'metrics:edit'


class MetricDetail(DetailView):
    model = Metric


class MetricCreation(CreateView):
    model = Metric
    form_class = MetricForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "visit" in self.request.GET:
            try:
                context['visit'] = Visit.objects.get(id=self.request.GET["visit"])
            except Visit.DoesNotExist:
                pass
        if "patient" in self.request.GET:
            try:
                context['patient'] = Patient.objects.get(id=self.request.GET["patient"])
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
        if not form.cleaned_data.get('visit'):
            patient = form.cleaned_data.get('patient')
            visit = Visit.objects.create(patient=patient)
            form.instance.visit = visit
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('visits:detail',args=(self.object.visit.id,))
    # fields = ['visit.patient', 'weight', 'height']


class MetricUpdate(UpdateView):
    model = Metric
    form_class = MetricForm

    def get_success_url(self):
        return reverse('visits:detail',args=(self.object.visit.id,))


class MetricDelete(DeleteView):
    model = Metric
    success_url = reverse_lazy('metrics:list')


class EnvironmentMetricCreation(CreateView):
    model = EnvironmentMetric
    fields = ['visit', 'dietary_diversity_score', 'breastfeeding', 'immunization_up_to_date', 'recent_illness',
              'recent_illness_type', 'notes']

    def get_initial(self):
        initial = super().get_initial()
        if "visit" in self.request.GET:
            initial["visit"] = self.request.GET["visit"]
        return initial

    def get_success_url(self):
        return reverse('visits:detail', args=(self.object.visit.id,))


class EnvironmentMetricUpdate(UpdateView):
    model = EnvironmentMetric
    fields = ['dietary_diversity_score', 'breastfeeding', 'immunization_up_to_date', 'recent_illness',
              'recent_illness_type', 'notes']

    def get_success_url(self):
        return reverse('visits:detail', args=(self.object.visit.id,))


class HouseholdStatusCreation(CreateView):
    model = HouseholdStatus
    fields = ['family', 'water_source', 'sanitation_type', 'floor_material', 'wall_material', 'roof_material',
              'household_income_proxy']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "family" in self.request.GET:
            context['family'] = Family.objects.get(id=self.request.GET["family"])
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
        return reverse('patients:list')


class HouseholdStatusUpdate(UpdateView):
    model = HouseholdStatus
    fields = ['water_source', 'sanitation_type', 'floor_material', 'wall_material', 'roof_material',
              'household_income_proxy']

    def get_success_url(self):
        if "next" in self.request.GET:
            return self.request.GET["next"]
        return reverse('patients:list')

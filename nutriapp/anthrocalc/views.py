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
    fields = ['name', 'dob', 'family']


class PatientUpdate(UpdateView):
    model = Patient
    success_url = reverse_lazy('patients:list')
    fields = ['name', 'dob', 'family']


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
    # success_url = reverse_lazy('visits:list')
    fields = "__all__"

    # def get_context_data(self, **kwargs):
    #     context = super().get_context_data(**kwargs)
    #     if "visit" in self.request.GET:
    #         visit_id = self.request.GET["visit"]
    #         context['visit'] = Visit.objects.filter(id=visit_id)
    #     return context

    def get_initial(self):
        initial = super().get_initial()
        if "visit" in self.request.GET:
            visit_id = self.request.GET["visit"]
            initial["visit"] = visit_id
        return initial

    def get_success_url(self):
        return reverse('visits:detail',args=(self.object.visit.id,))
    # fields = ['visit.patient', 'weight', 'height']


class MetricUpdate(UpdateView):
    model = Metric
    fields = ['weight', 'height', 'standing_or_upright']

    def get_success_url(self):
        return reverse('visits:detail',args=(self.object.visit.id,))


class MetricDelete(DeleteView):
    model = Metric
    success_url = reverse_lazy('metrics:list')

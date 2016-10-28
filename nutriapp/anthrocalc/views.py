from django.core.urlresolvers import reverse_lazy
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView
)
from .models import *


# Views for Patients

class PatientList(ListView):
    model = Patient


class PatientDetail(DetailView):
    model = Patient


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


class VisitList(ListView):
    model = Visit


class VisitDetail(DetailView):
    model = Visit


class VisitCreation(CreateView):
    model = Visit
    success_url = reverse_lazy('Visits:list')
    fields = ['patient', 'date']
    # TODO: add creator with patient id.


class VisitUpdate(UpdateView):
    model = Visit
    success_url = reverse_lazy('Visits:list')
    fields = ['patient', 'date']


class VisitDelete(DeleteView):
    model = Visit
    success_url = reverse_lazy('Visits:list')


# Views for Metrics


class MetricList(ListView):
    model = Metric


class MetricDetail(DetailView):
    model = Metric


class MetricCreation(CreateView):
    model = Metric
    success_url = reverse_lazy('Visits:list')
    fields = ['visit.patient', 'weight', 'height']


class MetricUpdate(UpdateView):
    model = Metric
    success_url = reverse_lazy('Metric:list')
    fields = ['visit.patient', 'weight', 'height']


class MetricDelete(DeleteView):
    model = Metric
    success_url = reverse_lazy('Metric:list')

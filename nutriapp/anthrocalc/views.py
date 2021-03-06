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



# Views for Patients

class PatientList(ListView):
    model = Patient


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


class VisitList(ListView):
    model = Visit

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


class MetricList(ListView):
    model = Metric


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

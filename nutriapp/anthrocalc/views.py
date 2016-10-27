from django.core.urlresolvers import reverse_lazy
from django.views.generic import ListView
from django.views.generic.detail import DetailView
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    DeleteView
)
from .models import *


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
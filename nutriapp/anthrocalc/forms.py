from django import forms
from .models import Metric, Patient, Visit

class MetricForm(forms.ModelForm):
    patient = forms.ModelChoiceField(queryset=Patient.objects.all(), required=False, label="Paciente (para crear visita implícita)")

    class Meta:
        model = Metric
        fields = [
            'visit', 'patient', 'weight', 'height', 'standing_or_upright', 
            'muac', 'edema', 'diarrhea',
            'intractable_vomiting', 'convulsions', 'lethargy_not_alert', 
            'unconsciousness', 'hypoglycemia', 'high_fever', 'hypothermia', 
            'severe_dehydration', 'lower_respiratory_tract_infection', 
            'severe_anemia', 'eye_signs_vit_a', 'skin_lesions'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If visit is provided, patient is not strictly needed for creation here, 
        # but we might want to make visit optional if patient is provided.
        self.fields['visit'].required = False

    def clean(self):
        cleaned_data = super().clean()
        visit = cleaned_data.get("visit")
        patient = cleaned_data.get("patient")

        if not visit and not patient:
            raise forms.ValidationError("Debe seleccionar una visita existente o un paciente para crear una nueva visita.")
        return cleaned_data

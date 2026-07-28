from django import forms
from .models import Metric, Patient, Visit, Family


class PatientForm(forms.ModelForm):
    new_family_name = forms.CharField(
        max_length=255,
        required=False,
        label="O crear nueva familia (nombre del responsable)",
        help_text="Si no selecciona una familia arriba, puede ingresar el nombre de una nueva aquí.",
    )

    class Meta:
        model = Patient
        fields = [
            "code",
            "name",
            "gender",
            "dob",
            "family",
            "mother_name",
            "birth_weight",
            "birth_length",
            "maternal_education",
        ]

    field_order = [
        "code",
        "name",
        "gender",
        "dob",
        "family",
        "new_family_name",
        "mother_name",
        "birth_weight",
        "birth_length",
        "maternal_education",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["family"].required = False

    def clean(self):
        cleaned_data = super().clean()
        family = cleaned_data.get("family")
        new_family_name = cleaned_data.get("new_family_name")

        if not family and not new_family_name:
            self.add_error("family", "Debe seleccionar una familia existente o ingresar el nombre para una nueva.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_family_name = self.cleaned_data.get("new_family_name")
        family = self.cleaned_data.get("family")

        if not family and new_family_name:
            family = Family.objects.create(responsible_name=new_family_name)
            instance.family = family

        if commit:
            instance.save()
        return instance


class MetricForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        queryset=Patient.objects.all(), required=False, label="Paciente (para crear visita implícita)"
    )

    class Meta:
        model = Metric
        fields = [
            "visit",
            "patient",
            "weight",
            "height",
            "standing_or_upright",
            "muac",
            "edema",
            "diarrhea",
            "intractable_vomiting",
            "convulsions",
            "lethargy_not_alert",
            "unconsciousness",
            "hypoglycemia",
            "high_fever",
            "hypothermia",
            "severe_dehydration",
            "lower_respiratory_tract_infection",
            "severe_anemia",
            "eye_signs_vit_a",
            "skin_lesions",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If visit is provided, patient is not strictly needed for creation here,
        # but we might want to make visit optional if patient is provided.
        self.fields["visit"].required = False

    def clean(self):
        cleaned_data = super().clean()
        visit = cleaned_data.get("visit")
        patient = cleaned_data.get("patient")

        if not visit and not patient:
            raise forms.ValidationError(
                "Debe seleccionar una visita existente o un paciente para crear una nueva visita."
            )
        return cleaned_data

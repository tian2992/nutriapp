import datetime
from django import forms
from django.forms import formset_factory
from .models import Metric, Patient, Visit, Family, Community


class CommunityForm(forms.ModelForm):
    class Meta:
        model = Community
        fields = ["name", "municipality", "department", "contact_person", "notes"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "municipality": forms.TextInput(attrs={"class": "form-control"}),
            "department": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class PatientForm(forms.ModelForm):
    community = forms.ModelChoiceField(
        queryset=Community.objects.all(),
        required=False,
        label="Comunidad",
        help_text="Asignar la comunidad de la familia.",
    )
    new_community_name = forms.CharField(
        max_length=200,
        required=False,
        label="O crear nueva comunidad",
        help_text="Si no selecciona una comunidad arriba, puede ingresar el nombre de una nueva aquí.",
    )
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
            "community",
            "new_community_name",
            "family",
            "new_family_name",
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
        "community",
        "new_community_name",
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
        if self.instance and self.instance.pk and self.instance.family:
            if self.instance.family.community:
                self.fields["community"].initial = self.instance.family.community
        elif "initial" in kwargs and "community" in kwargs["initial"]:
            self.fields["community"].initial = kwargs["initial"]["community"]

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
        community = self.cleaned_data.get("community")
        new_community_name = self.cleaned_data.get("new_community_name")

        if new_community_name:
            community, _ = Community.objects.get_or_create(name=new_community_name)

        if not family and new_family_name:
            family = Family.objects.create(responsible_name=new_family_name, community=community)
            instance.family = family
        elif family:
            if community and family.community != community:
                family.community = community
                family.save(update_fields=["community"])
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


class MassMeasurementHeaderForm(forms.Form):
    date = forms.DateField(
        initial=datetime.date.today,
        label="Fecha de Jornada",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    responsible_name = forms.CharField(
        max_length=200,
        required=False,
        label="Encargado / Promotor",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre del promotor o encargado"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notas de la Jornada",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Observaciones generales de la jornada..."}),
    )


class MassMeasurementRowForm(forms.Form):
    patient_id = forms.IntegerField(widget=forms.HiddenInput())
    weight = forms.FloatField(
        required=False,
        min_value=0.5,
        max_value=150.0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end", "step": "0.01", "placeholder": "kg"}),
    )
    height = forms.FloatField(
        required=False,
        min_value=20.0,
        max_value=250.0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end", "step": "0.1", "placeholder": "cm"}),
    )
    standing_or_upright = forms.ChoiceField(
        choices=[("", "-- Posición --"), ("False", "Acostado"), ("True", "De pie")],
        required=False,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    muac = forms.FloatField(
        required=False,
        min_value=5.0,
        max_value=50.0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm text-end", "step": "0.1", "placeholder": "cm"}),
    )
    edema = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Notas / Signos"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        weight = cleaned_data.get("weight")
        height = cleaned_data.get("height")

        if (weight is not None and height is None) or (weight is None and height is not None):
            raise forms.ValidationError("Debe ingresar tanto el peso como la altura para registrar la medición.")

        return cleaned_data

    def has_data(self):
        cleaned_data = getattr(self, "cleaned_data", {})
        return bool(cleaned_data.get("weight") is not None and cleaned_data.get("height") is not None)


class BaseMassMeasurementFormSet(forms.BaseFormSet):
    pass

import datetime
from django import forms
from django.forms import formset_factory
from .models import (
    ENVIRONMENT_YES_NO_FLAGS,
    METRIC_CLINICAL_FLAGS,
    Community,
    EnvironmentMetric,
    Family,
    Metric,
    MultipleVisit,
    Patient,
    Visit,
)

# Posted values are the strings a <select> submits. True/False are also
# accepted so existing tests that post real booleans still validate.
YES_NO_UNKNOWN_CHOICES = (
    ("", "Sin dato"),
    ("True", "Sí"),
    ("False", "No"),
)


def coerce_yes_no_unknown(value):
    if value in (True, "True", "true", "1"):
        return True
    if value in (False, "False", "false", "0"):
        return False
    return None


class YesNoUnknownFormField(forms.TypedChoiceField):
    """Sí / No / Sin dato, stored as True / False / None."""

    def __init__(self, **kwargs):
        widget_attrs = kwargs.pop("widget_attrs", None)
        kwargs.setdefault("choices", YES_NO_UNKNOWN_CHOICES)
        kwargs.setdefault("coerce", coerce_yes_no_unknown)
        kwargs.setdefault("empty_value", None)
        kwargs.setdefault("required", False)
        if "widget" not in kwargs:
            attrs = {"class": "form-select"}
            if widget_attrs:
                attrs.update(widget_attrs)
            kwargs["widget"] = forms.Select(attrs=attrs)
        super().__init__(**kwargs)


def use_yes_no_unknown_fields(form, names):
    for name in names:
        if name not in form.fields:
            continue
        current = form.fields[name]
        form.fields[name] = YesNoUnknownFormField(
            label=current.label,
            help_text=current.help_text,
            required=False,
        )


def jornadas_for_patient(patient):
    """Jornadas (MultipleVisit) belonging to the patient's community only."""
    if patient is None:
        return MultipleVisit.objects.none()
    community = getattr(patient, "community", None)
    if community is None:
        return MultipleVisit.objects.none()
    return MultipleVisit.objects.filter(community=community).order_by("-date")


def _resolve_patient(*, data=None, initial=None, instance=None, patient_field="patient"):
    """Best-effort patient from POST data, initial, or a model instance."""
    raw = None
    if data is not None:
        raw = data.get(patient_field)
    if not raw and initial:
        raw = initial.get(patient_field)
    if raw:
        if isinstance(raw, Patient):
            return raw
        try:
            return Patient.objects.select_related("family__community").get(pk=raw)
        except (Patient.DoesNotExist, TypeError, ValueError):
            return None
    if instance is not None and getattr(instance, "pk", None):
        related = getattr(instance, patient_field, None)
        if isinstance(related, Patient):
            return related
    return None


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
        self.fields["code"].required = False
        self.fields["code"].help_text = "Opcional. Si se deja vacío, se genera automáticamente (QA + municipio + comunidad + número)."
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
        code = (cleaned_data.get("code") or "").strip()
        cleaned_data["code"] = code

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

        # Ensure family/community are set before Patient.save() autogenerates the code.
        if commit:
            instance.save()
        return instance


class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["patient", "date", "notes", "multiple_visit"]
        labels = {
            "multiple_visit": "Jornada",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["multiple_visit"].required = False
        self.fields["notes"].required = False
        patient = _resolve_patient(
            data=self.data or None,
            initial=self.initial,
            instance=self.instance if self.instance.pk else None,
        )
        self.fields["multiple_visit"].queryset = jornadas_for_patient(patient)

    def clean(self):
        cleaned_data = super().clean()
        patient = cleaned_data.get("patient")
        multiple_visit = cleaned_data.get("multiple_visit")
        if multiple_visit and patient:
            community = patient.community
            if community is None or multiple_visit.community_id != community.id:
                self.add_error(
                    "multiple_visit",
                    "La jornada debe pertenecer a la comunidad del paciente.",
                )
        return cleaned_data


class MetricForm(forms.ModelForm):
    patient = forms.ModelChoiceField(
        queryset=Patient.objects.all(), required=False, label="Paciente (para crear visita implícita)"
    )
    multiple_visit = forms.ModelChoiceField(
        queryset=MultipleVisit.objects.none(),
        required=False,
        label="Jornada",
        help_text="Solo jornadas de la comunidad del paciente.",
    )

    class Meta:
        model = Metric
        fields = [
            "visit",
            "patient",
            "multiple_visit",
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

        patient = _resolve_patient(
            data=self.data or None,
            initial=self.initial,
            instance=None,
        )
        if patient is None and self.data.get("visit"):
            try:
                visit = Visit.objects.select_related("patient__family__community").get(
                    pk=self.data.get("visit")
                )
                patient = visit.patient
            except (Visit.DoesNotExist, TypeError, ValueError):
                pass
        elif patient is None and self.initial.get("visit"):
            visit = self.initial["visit"]
            if isinstance(visit, Visit):
                patient = visit.patient
            else:
                try:
                    visit = Visit.objects.select_related("patient__family__community").get(pk=visit)
                    patient = visit.patient
                except (Visit.DoesNotExist, TypeError, ValueError):
                    pass

        # Jornada only applies when creating an implicit visit for a patient.
        if self.initial.get("visit") or (self.data and self.data.get("visit")):
            self.fields["multiple_visit"].queryset = MultipleVisit.objects.none()
            self.fields["multiple_visit"].widget = forms.HiddenInput()
        else:
            self.fields["multiple_visit"].queryset = jornadas_for_patient(patient)

        use_yes_no_unknown_fields(self, METRIC_CLINICAL_FLAGS)

    def clean(self):
        cleaned_data = super().clean()
        visit = cleaned_data.get("visit")
        patient = cleaned_data.get("patient")
        multiple_visit = cleaned_data.get("multiple_visit")

        if not visit and not patient:
            raise forms.ValidationError(
                "Debe seleccionar una visita existente o un paciente para crear una nueva visita."
            )

        if visit:
            cleaned_data["multiple_visit"] = None
        elif multiple_visit and patient:
            community = patient.community
            if community is None or multiple_visit.community_id != community.id:
                self.add_error(
                    "multiple_visit",
                    "La jornada debe pertenecer a la comunidad del paciente.",
                )
        return cleaned_data


class EnvironmentMetricForm(forms.ModelForm):
    class Meta:
        model = EnvironmentMetric
        fields = [
            "dietary_diversity_score",
            "breastfeeding",
            "immunization_up_to_date",
            "recent_illness",
            "recent_illness_type",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        use_yes_no_unknown_fields(self, ENVIRONMENT_YES_NO_FLAGS)


class EnvironmentMetricCreateForm(EnvironmentMetricForm):
    class Meta(EnvironmentMetricForm.Meta):
        fields = ["visit", *EnvironmentMetricForm.Meta.fields]


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
    edema = YesNoUnknownFormField(
        label="Edema",
        widget_attrs={"class": "form-select form-select-sm"},
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

from django.conf import settings
from django.db import models
from django.utils.timezone import now
from django.urls import reverse

# Create your models here.


class Community(models.Model):
    """Represents a geographical community, village, or sector."""

    name = models.CharField(max_length=200, verbose_name="Nombre de la comunidad")
    municipality = models.CharField(
        max_length=150, blank=True, default="Rabinal", verbose_name="Municipio"
    )
    department = models.CharField(
        max_length=150, blank=True, default="Baja Verapaz", verbose_name="Departamento"
    )
    contact_person = models.CharField(
        max_length=200, blank=True, verbose_name="Líder / Promotor encargado"
    )
    notes = models.TextField(blank=True, null=True, verbose_name="Notas")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comunidad"
        verbose_name_plural = "Comunidades"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.municipality})"

    def get_absolute_url(self):
        return reverse("communities:detail", args=[str(self.id)])


class Family(models.Model):
    responsible_name = models.TextField(null=False)
    community = models.ForeignKey(
        Community,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="families",
        verbose_name="Comunidad",
    )
    allowed_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="accessible_families",
        verbose_name="Usuarios con acceso",
    )

    def __str__(self):
        return self.responsible_name


class WaterSource(models.Model):
    name = models.CharField(max_length=100, verbose_name="Fuente de agua")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Fuente de agua"
        verbose_name_plural = "Fuentes de agua"


class SanitationType(models.Model):
    name = models.CharField(max_length=100, verbose_name="Tipo de saneamiento")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Tipo de saneamiento"
        verbose_name_plural = "Tipos de saneamiento"


class FloorMaterial(models.Model):
    name = models.CharField(max_length=100, verbose_name="Material del piso")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Material del piso"
        verbose_name_plural = "Materiales del piso"


class WallMaterial(models.Model):
    name = models.CharField(max_length=100, verbose_name="Material de la pared")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Material de la pared"
        verbose_name_plural = "Materiales de la pared"


class RoofMaterial(models.Model):
    name = models.CharField(max_length=100, verbose_name="Material del techo")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Material del techo"
        verbose_name_plural = "Materiales del techo"


class HouseholdStatus(models.Model):
    INCOME_PROXY_CHOICES = [
        ("low", "Bajo"),
        ("medium", "Medio"),
        ("high", "Alto"),
    ]

    family = models.OneToOneField(Family, on_delete=models.CASCADE, related_name="status", verbose_name="Familia")
    water_source = models.ForeignKey(
        WaterSource, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Fuente de agua"
    )
    sanitation_type = models.ForeignKey(
        SanitationType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Tipo de saneamiento"
    )
    floor_material = models.ForeignKey(
        FloorMaterial, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Material del piso"
    )
    wall_material = models.ForeignKey(
        WallMaterial, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Material de las paredes"
    )
    roof_material = models.ForeignKey(
        RoofMaterial, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Material del techo"
    )
    household_income_proxy = models.CharField(
        max_length=20, choices=INCOME_PROXY_CHOICES, null=True, blank=True, verbose_name="Proxy de ingresos del hogar"
    )

    def __str__(self):
        return f"Estado de hogar: {self.family.responsible_name}"

    class Meta:
        verbose_name = "Estado de hogar"
        verbose_name_plural = "Estados de hogar"


class Patient(models.Model):
    MATERNAL_EDUCATION_CHOICES = [
        ("none", "Ninguna"),
        ("primary", "Primaria"),
        ("secondary", "Secundaria"),
        ("higher", "Superior"),
    ]

    id = models.AutoField(primary_key=True)
    # Full Name
    code = models.CharField(max_length=50, verbose_name="Código")
    name = models.CharField(max_length=250, verbose_name="Nombre")

    # M or F
    gender = models.CharField(max_length=1, verbose_name="Sexo")

    # Day of Birth
    dob = models.DateField(verbose_name="Fecha de Nacimiento")

    family = models.ForeignKey(Family, on_delete=models.SET_NULL, null=True, verbose_name="Familia")

    # New fields for Step 2
    mother_name = models.CharField(max_length=250, null=True, blank=True, verbose_name="Nombre de la madre")
    birth_weight = models.FloatField(null=True, blank=True, verbose_name="Peso al nacer (kg)")
    birth_length = models.FloatField(null=True, blank=True, verbose_name="Talla al nacer (cm)")
    maternal_education = models.CharField(
        max_length=20, choices=MATERNAL_EDUCATION_CHOICES, null=True, blank=True, verbose_name="Educación materna"
    )
    risk_score = models.FloatField(null=True, blank=True, verbose_name="Puntaje de riesgo")

    notes = models.TextField(null=True, blank=True, verbose_name="Notas")

    @property
    def community(self):
        return self.family.community if self.family else None

    def get_absolute_url(self):
        return reverse("patients:detail", args=[str(self.id)])

    def __str__(self):
        return " de ".join([self.name, self.family.responsible_name])

    # TODO: moar info


class MultipleVisit(models.Model):
    """Represents a measurement round (jornada) in a specific community."""

    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name="multiple_visits",
        verbose_name="Comunidad",
    )
    date = models.DateTimeField(default=now, verbose_name="Fecha de jornada")
    responsible_name = models.CharField(
        max_length=200, blank=True, verbose_name="Encargado de medición"
    )
    notes = models.TextField(blank=True, null=True, verbose_name="Notas de la jornada")

    class Meta:
        verbose_name = "Jornada / Visita Masiva"
        verbose_name_plural = "Jornadas / Visitas Masivas"
        ordering = ["-date"]

    def __str__(self):
        return f"Jornada {self.community.name} - {self.date.strftime('%Y-%m-%d')}"


# A point in time where metrics are taken
class Visit(models.Model):
    # def __init__(self, *args, **kwargs):
    #     super(Visit, self).__init__(*args, **kwargs)
    #
    # def __init__(self, multiple_visit, *args, **kwargs):
    #     super(Visit, self).__init__(*args, **kwargs)
    #     self.date = multiple_visit.date

    # TODO: check UTC policy
    # https://docs.djangoproject.com/en/1.10/ref/models/fields/#django.db.models.DateField.auto_now_add
    date = models.DateTimeField(default=now)
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    notes = models.TextField(verbose_name="Notas", null=True, blank=True)
    multiple_visit = models.ForeignKey(MultipleVisit, on_delete=models.CASCADE, null=True, blank=True)

    def get_absolute_url(self):
        return reverse("visits:detail", args=[str(self.id)])

    def __str__(self):
        return "{} - {}".format(self.patient.name, self.date)


class Metric(models.Model):
    weight = models.FloatField(verbose_name="Peso (kg)")
    height = models.FloatField(verbose_name="Altura (cm)")
    standing_or_upright = models.BooleanField(null=True, verbose_name="¿Fue medido de pie / parado?")

    # New clinical fields for Step 1
    muac = models.FloatField(null=True, blank=True, verbose_name="MUAC (cm)")

    # Danger signs / Complications
    edema = models.BooleanField(default=False, verbose_name="Edema")
    diarrhea = models.BooleanField(default=False, verbose_name="Diarrea")
    intractable_vomiting = models.BooleanField(default=False, verbose_name="Vómitos incoercibles")
    convulsions = models.BooleanField(default=False, verbose_name="Convulsiones")
    lethargy_not_alert = models.BooleanField(default=False, verbose_name="Letargo / No alerta")
    unconsciousness = models.BooleanField(default=False, verbose_name="Inconsciencia")
    hypoglycemia = models.BooleanField(default=False, verbose_name="Hipoglucemia")
    high_fever = models.BooleanField(default=False, verbose_name="Fiebre alta")
    hypothermia = models.BooleanField(default=False, verbose_name="Hipotermia")
    severe_dehydration = models.BooleanField(default=False, verbose_name="Deshidratación severa")
    lower_respiratory_tract_infection = models.BooleanField(
        default=False, verbose_name="Infección de las vías respiratorias bajas"
    )
    severe_anemia = models.BooleanField(default=False, verbose_name="Anemia severa")
    eye_signs_vit_a = models.BooleanField(default=False, verbose_name="Signos oculares de deficiencia de Vit A")
    skin_lesions = models.BooleanField(default=False, verbose_name="Lesiones cutáneas")

    # Z-score cache fields for Step 1
    wfaz = models.FloatField(null=True, blank=True, verbose_name="WAZ (Peso para la Edad)")
    hfaz = models.FloatField(null=True, blank=True, verbose_name="HAZ (Talla para la Edad)")
    wfhz = models.FloatField(null=True, blank=True, verbose_name="WHZ (Peso para la Talla)")
    bmi_age = models.FloatField(null=True, blank=True, verbose_name="BMI-AGE (Indice de Masa Corporal)")

    visit = models.OneToOneField(
        Visit, on_delete=models.CASCADE, verbose_name="Visita"
    )  # TODO: check this relationship

    def save(self, *args, **kwargs):
        from .person_utils import calculate_zscore_for_metric

        calculate_zscore_for_metric(self)
        super(Metric, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("metrics:detail", args=[str(self.id)])

    def __str__(self):
        return "weight: {} - height: {}".format(self.weight, self.height)


## A visit includes a set of metrics, given the living conditions
class EnvironmentMetric(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)

    # Per-visit observations
    dietary_diversity_score = models.IntegerField(
        null=True, blank=True, verbose_name="Puntaje de diversidad dietética (0-9)"
    )
    breastfeeding = models.BooleanField(default=False, verbose_name="Lactancia materna")
    immunization_up_to_date = models.BooleanField(default=False, verbose_name="Inmunización al día")
    recent_illness = models.BooleanField(default=False, verbose_name="Enfermedad reciente")
    recent_illness_type = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Tipo de enfermedad reciente"
    )
    notes = models.TextField(null=True, blank=True, verbose_name="Notas")

    def __str__(self):
        return f"Observaciones de entorno: {self.visit}"


# Treatments or actions taken to fix the condition
class Action(models.Model):
    action_type = models.TextField()
    value = models.TextField()

    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)  # TODO: check this relationship

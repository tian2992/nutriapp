from django.contrib import admin
from .models import *


class HouseholdStatusInline(admin.StackedInline):
    model = HouseholdStatus
    can_delete = False


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    inlines = [HouseholdStatusInline]
    search_fields = ("responsible_name",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "dob")
    search_fields = ("code", "name")
    list_filter = ("family",)


class MetricInline(admin.TabularInline):
    model = Metric
    extra = 1


class EnvironmentMetricInline(admin.TabularInline):
    model = EnvironmentMetric
    extra = 1


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("patient", "date")
    list_filter = ("date", "patient")
    inlines = [MetricInline, EnvironmentMetricInline]


@admin.register(WaterSource)
class WaterSourceAdmin(admin.ModelAdmin):
    pass


@admin.register(SanitationType)
class SanitationTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(FloorMaterial)
class FloorMaterialAdmin(admin.ModelAdmin):
    pass


@admin.register(WallMaterial)
class WallMaterialAdmin(admin.ModelAdmin):
    pass


@admin.register(RoofMaterial)
class RoofMaterialAdmin(admin.ModelAdmin):
    pass


@admin.register(HouseholdStatus)
class HouseholdStatusAdmin(admin.ModelAdmin):
    list_display = ("family", "water_source", "sanitation_type", "household_income_proxy")


@admin.register(EnvironmentMetric)
class EnvironmentMetricAdmin(admin.ModelAdmin):
    list_display = ("visit", "dietary_diversity_score", "recent_illness")


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ("visit", "weight", "height", "wfaz", "hfaz", "wfhz")


admin.site.register(Action)
admin.site.register(MultipleVisit)

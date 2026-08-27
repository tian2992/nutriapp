from django.contrib import admin
from .models import *


class HouseholdStatusInline(admin.StackedInline):
    model = HouseholdStatus
    extra = 0
    ordering = ("-recorded_at",)


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality", "department", "contact_person", "created_at")
    search_fields = ("name", "municipality", "department", "contact_person")
    list_filter = ("municipality", "department")


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality", "department", "contact_person", "created_at")
    search_fields = ("name", "municipality", "department", "contact_person")
    list_filter = ("municipality", "department")


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("responsible_name", "community")
    inlines = [HouseholdStatusInline]
    search_fields = ("responsible_name",)
    list_filter = ("community",)


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "get_community", "dob")
    search_fields = ("code", "name")
    list_filter = ("family__community", "family")

    @admin.display(description="Comunidad")
    def get_community(self, obj):
        return obj.community


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
    list_display = ("family", "recorded_at", "water_source", "sanitation_type", "household_income_proxy")
    list_filter = ("recorded_at", "water_source", "sanitation_type", "household_income_proxy")
    search_fields = ("family__responsible_name",)
    date_hierarchy = "recorded_at"


@admin.register(EnvironmentMetric)
class EnvironmentMetricAdmin(admin.ModelAdmin):
    list_display = ("visit", "dietary_diversity_score", "recent_illness")


@admin.register(Metric)
class MetricAdmin(admin.ModelAdmin):
    list_display = ("visit", "weight", "height", "wfaz", "hfaz", "wfhz")


@admin.register(MultipleVisit)
class MultipleVisitAdmin(admin.ModelAdmin):
    list_display = ("community", "date", "responsible_name")
    search_fields = ("community__name", "responsible_name", "notes")
    list_filter = ("community", "date")


admin.site.register(Action)

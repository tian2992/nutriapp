from django import forms
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.template.response import TemplateResponse
from django.urls import path

from .models import *


class HouseholdStatusInline(admin.StackedInline):
    model = HouseholdStatus
    can_delete = False


class FamilyAdminForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ["responsible_name", "allowed_users"]


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    form = FamilyAdminForm
    inlines = [HouseholdStatusInline]
    search_fields = ("responsible_name",)
    filter_horizontal = ("allowed_users",)
    list_display = ("responsible_name", "allowed_users_count", "patient_count")
    list_filter = ("allowed_users",)
    ordering = ("responsible_name",)

    def allowed_users_count(self, obj):
        return obj.allowed_users.count()

    def patient_count(self, obj):
        return obj.patient_set.count()

    allowed_users_count.short_description = "Usuarios con acceso"
    patient_count.short_description = "Pacientes"


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "dob")
    search_fields = ("code", "name")
    list_filter = ("family",)
    ordering = ("name",)


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


@staff_member_required
def family_access_summary(request):
    families = Family.objects.prefetch_related("allowed_users").order_by("responsible_name")
    context = {
        "title": "Resumen de acceso por familia",
        "families": families,
        "opts": Family._meta,
    }
    return TemplateResponse(request, "admin/anthrocalc/family_access_summary.html", context)


admin.site.register(Action)
admin.site.register(MultipleVisit)

admin.site.index_template = "admin/anthrocalc/index.html"


original_get_urls = admin.site.get_urls


def get_admin_urls():
    urls = original_get_urls()
    custom_urls = [
        path(
            "anthrocalc/family-access-summary/",
            admin.site.admin_view(family_access_summary),
            name="anthrocalc_family_access_summary",
        ),
    ]
    return custom_urls + urls


admin.site.get_urls = get_admin_urls

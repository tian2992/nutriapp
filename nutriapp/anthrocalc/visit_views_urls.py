from django.urls import path
from .views import (
    VisitList,
    VisitDetail,
    VisitCreation,
    VisitUpdate,
    VisitDelete,
    EnvironmentMetricCreation,
    EnvironmentMetricUpdate,
    HouseholdStatusCreation,
    HouseholdStatusUpdate,
)


app_name = "nutriapp"

urlpatterns = [
    path("visit/", VisitList.as_view(), name="list"),
    path("visit/<int:pk>", VisitDetail.as_view(), name="detail"),
    path("visit/new", VisitCreation.as_view(), name="new"),
    path("visit/edit/<int:pk>", VisitUpdate.as_view(), name="edit"),
    path("visit/delete/<int:pk>", VisitDelete.as_view(), name="delete"),
    path("visit/environment/new", EnvironmentMetricCreation.as_view(), name="env_new"),
    path("visit/environment/edit/<int:pk>", EnvironmentMetricUpdate.as_view(), name="env_edit"),
    path("family/status/new", HouseholdStatusCreation.as_view(), name="household_new"),
    path("family/status/edit/<int:pk>", HouseholdStatusUpdate.as_view(), name="household_edit"),
]

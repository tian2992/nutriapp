from django.urls import path
from .views import PatientList, PatientDetail, PatientCreation, PatientUpdate, PatientDelete

app_name = "nutriapp"


urlpatterns = [
    path("patient/", PatientList.as_view(), name="list"),
    path("patient/<int:pk>", PatientDetail.as_view(), name="detail"),
    path("patient/new", PatientCreation.as_view(), name="new"),
    path("patient/edit/<int:pk>", PatientUpdate.as_view(), name="edit"),
    path("patient/delete/<int:pk>", PatientDelete.as_view(), name="delete"),
]

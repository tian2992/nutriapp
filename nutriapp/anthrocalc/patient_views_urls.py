from django.conf.urls import url
from .views import (
    PatientList,
    PatientDetail,
    PatientCreation,
    PatientUpdate,
    PatientDelete
)



app_name="nutriapp"


urlpatterns = [
    url(r'^patient/$', PatientList.as_view(), name='list'),
    url(r'^patient/(?P<pk>\d+)$', PatientDetail.as_view(), name='detail'),
    url(r'^patient/new$', PatientCreation.as_view(), name='new'),
    url(r'^patient/edit/(?P<pk>\d+)$', PatientUpdate.as_view(), name='edit'),
    url(r'^patient/delete/(?P<pk>\d+)$', PatientDelete.as_view(), name='delete'),
]

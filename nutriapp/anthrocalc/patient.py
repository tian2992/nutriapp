from django.conf.urls import url
from .views import (
    PatientList,
    PatientDetail,
    PatientCreation,
    PatientUpdate,
    PatientDelete
)

urlpatterns = [
    url(r'^patient/$', PatientList.as_view(), name='patient:list'),
    url(r'^patient/(?P<pk>\d+)$', PatientDetail.as_view(), name='patient:detail'),
    url(r'^patient/new$', PatientCreation.as_view(), name='patient:new'),
    url(r'^patient/edit/(?P<pk>\d+)$', PatientUpdate.as_view(), name='patient:edit'),
    url(r'^patient/delete/(?P<pk>\d+)$', PatientDelete.as_view(), name='patient:delete'),
]
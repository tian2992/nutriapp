from django.conf.urls import url
from .views import (
    MetricList,
    MetricDetail,
    MetricCreation,
    MetricUpdate,
    MetricDelete
)

app_name="nutriapp"

urlpatterns = [
    url(r'^metrics/$', MetricList.as_view(), name='list'),
    url(r'^metric/(?P<pk>\d+)$', MetricDetail.as_view(), name='detail'),
    url(r'^metric/new$', MetricCreation.as_view(), name='new'), ## FIXME with ID of kid
    url(r'^metric/new/with_visit/(?P<visit>\d+)$', MetricCreation.as_view(), name='newvm'),
    url(r'^metric/edit/(?P<pk>\d+)$', MetricUpdate.as_view(), name='edit'),
    url(r'^metric/delete/(?P<pk>\d+)$', MetricDelete.as_view(), name='delete'),
]

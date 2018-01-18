from django.conf.urls import url
from .views import (
    VisitList,
    VisitDetail,
    VisitCreation,
    VisitUpdate,
    VisitDelete
)



app_name="nutriapp"

urlpatterns = [
    url(r'^visit/$', VisitList.as_view(), name='list'),
    url(r'^visit/(?P<pk>\d+)$', VisitDetail.as_view(), name='detail'),
    url(r'^visit/new$', VisitCreation.as_view(), name='new'),
    url(r'^visit/edit/(?P<pk>\d+)$', VisitUpdate.as_view(), name='edit'),
    url(r'^visit/delete/(?P<pk>\d+)$', VisitDelete.as_view(), name='delete'),
]

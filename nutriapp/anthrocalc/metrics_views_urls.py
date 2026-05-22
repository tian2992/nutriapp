from django.urls import path
from .views import (
    MetricList,
    MetricDetail,
    MetricCreation,
    MetricUpdate,
    MetricDelete
)

app_name="nutriapp"

urlpatterns = [
    path('metrics/', MetricList.as_view(), name='list'),
    path('metric/<int:pk>', MetricDetail.as_view(), name='detail'),
    path('metric/new', MetricCreation.as_view(), name='new'), ## FIXME with ID of kid
    path('metric/new/with_visit/<int:visit>', MetricCreation.as_view(), name='newvm'),
    path('metric/edit/<int:pk>', MetricUpdate.as_view(), name='edit'),
    path('metric/delete/<int:pk>', MetricDelete.as_view(), name='delete'),
]

from django.urls import path
from .views import (
    VisitList,
    VisitDetail,
    VisitCreation,
    VisitUpdate,
    VisitDelete
)



app_name="nutriapp"

urlpatterns = [
    path('visit/', VisitList.as_view(), name='list'),
    path('visit/<int:pk>', VisitDetail.as_view(), name='detail'),
    path('visit/new', VisitCreation.as_view(), name='new'),
    path('visit/edit/<int:pk>', VisitUpdate.as_view(), name='edit'),
    path('visit/delete/<int:pk>', VisitDelete.as_view(), name='delete'),
]

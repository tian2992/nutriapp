from django.urls import path
from .views import (
    CommunityList,
    CommunityDetail,
    CommunityCreation,
    CommunityUpdate,
    CommunityDelete,
    CommunityMassVisit,
)

app_name = "nutriapp"

urlpatterns = [
    path("communities/", CommunityList.as_view(), name="list"),
    path("communities/<int:pk>/", CommunityDetail.as_view(), name="detail"),
    path("communities/new/", CommunityCreation.as_view(), name="new"),
    path("communities/<int:pk>/edit/", CommunityUpdate.as_view(), name="edit"),
    path("communities/<int:pk>/delete/", CommunityDelete.as_view(), name="delete"),
    path("communities/<int:pk>/mass-visit/", CommunityMassVisit.as_view(), name="mass_visit"),
]

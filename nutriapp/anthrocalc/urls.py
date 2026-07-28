from django.urls import path

from .patient_graph import simple, graph_for_person


app_name = "nutriapp"

#
urlpatterns = [
    path("charts/simple.png", simple),
    path("charts/personal_progress.png", graph_for_person),
]

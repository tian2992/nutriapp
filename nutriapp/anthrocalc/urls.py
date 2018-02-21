from django.conf.urls import url

from .patient_graph import simple, graph_for_person



app_name="nutriapp"

#
urlpatterns = [
    url(r'charts/simple.png$', simple),
    url(r'charts/personal_progress.png$', graph_for_person),
]

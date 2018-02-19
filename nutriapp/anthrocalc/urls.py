from django.conf.urls import url

from .patient_graph import simple



app_name="nutriapp"

#
urlpatterns = [
    url(r'charts/simple.png$', simple),
]

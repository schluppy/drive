from django.urls import path

from . import views

app_name = "importe"

urlpatterns = [
    path("", views.hochladen, name="hochladen"),
    path("zuordnen/", views.zuordnen, name="zuordnen"),
]

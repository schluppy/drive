from django.urls import path

from . import views

app_name = "fahrzeuge"

urlpatterns = [
    path("", views.liste, name="liste"),
    path("neu/", views.bearbeiten, name="neu"),
    path("<int:fahrzeug_id>/", views.uebersicht, name="uebersicht"),
    path("<int:fahrzeug_id>/bearbeiten/", views.bearbeiten, name="bearbeiten"),
    path("<int:fahrzeug_id>/foto/", views.foto, name="foto"),
    path("<int:fahrzeug_id>/loeschen/", views.loeschen, name="loeschen"),
]

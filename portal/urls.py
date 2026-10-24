from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.start, name="start"),
    path("anmelden/", views.anmelden, name="anmelden"),
    path("anmelden/gesendet/", views.gesendet, name="gesendet"),
    path("anmelden/link/<str:token>/", views.token, name="token"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("familie/", views.familie, name="familie"),
    path("profil/", views.profil, name="profil"),
    path("datenschutz/", views.datenschutz, name="datenschutz"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
]

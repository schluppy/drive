from django.urls import path

from . import views

app_name = "auswertung"

urlpatterns = [
    path("vergleich/", views.vergleich, name="vergleich"),
    path("<int:fahrzeug_id>/statistik/", views.statistik, name="statistik"),
    path("<int:fahrzeug_id>/kosten/", views.kosten, name="kosten"),
]

from django.urls import path

from . import views

app_name = "logbuch"

urlpatterns = [
    path("kategorien/", views.kategorien, name="kategorien"),
    path("kategorien/neu/", views.kategorie_bearbeiten, name="kategorie_neu"),
    path("kategorien/<int:pk>/", views.kategorie_bearbeiten, name="kategorie"),
    path("eintrag/<int:pk>/", views.bearbeiten, name="bearbeiten"),
    path("eintrag/<int:pk>/loeschen/", views.loeschen, name="loeschen"),
    path("<int:fahrzeug_id>/", views.liste, name="liste"),
    path("<int:fahrzeug_id>/neu/<str:art>/", views.neu, name="neu"),
    path("<int:fahrzeug_id>/serien/", views.serien, name="serien"),
    path("<int:fahrzeug_id>/serien/neu/", views.serie_bearbeiten, name="serie_neu"),
    path("<int:fahrzeug_id>/serien/<int:pk>/", views.serie_bearbeiten, name="serie"),
    path("<int:fahrzeug_id>/erinnerungen/", views.erinnerungen, name="erinnerungen"),
    path("<int:fahrzeug_id>/erinnerungen/neu/", views.erinnerung_bearbeiten, name="erinnerung_neu"),
    path("<int:fahrzeug_id>/erinnerungen/<int:pk>/", views.erinnerung_bearbeiten, name="erinnerung"),
    path("<int:fahrzeug_id>/erinnerungen/<int:pk>/erledigt/", views.erinnerung_erledigt, name="erledigt"),
]

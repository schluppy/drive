from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Drive – Verwaltung"
admin.site.site_title = "Drive"
admin.site.index_title = "Familien und Personen"
admin.site.site_url = "/"

urlpatterns = [
    path("verwaltung/", admin.site.urls),
    path("fahrzeug/", include("fahrzeuge.urls")),
    path("logbuch/", include("logbuch.urls")),
    path("auswertung/", include("auswertung.urls")),
    path("import/", include("importe.urls")),
    path("", include("portal.urls")),
]

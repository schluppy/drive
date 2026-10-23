from django.apps import AppConfig
from django.db.models.signals import post_save


def _standardkategorien(sender, instance, created, **kwargs):
    if created:
        from .models import Kategorie
        Kategorie.standard_anlegen(instance)


class LogbuchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "logbuch"
    verbose_name = "Logbuch"

    def ready(self):
        # jede neue Familie bekommt die Kategorien aus DriveNote
        post_save.connect(_standardkategorien, sender="konten.Familie", dispatch_uid="standardkategorien")

"""Bucht fällige Serien (wiederkehrende Kosten) ins Logbuch. Täglich per Cron."""
from datetime import date

from django.core.management.base import BaseCommand

from logbuch.models import Serie
from logbuch.serien import buchen


class Command(BaseCommand):
    help = "Fällige Serien ins Logbuch buchen"

    def handle(self, **opts):
        n = sum(buchen(s) for s in Serie.objects.select_related("fahrzeug", "kategorie"))
        self.stdout.write(f"{date.today()}: {n} Einträge aus Serien gebucht")

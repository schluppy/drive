"""Merkt sich, wann eine angemeldete Person das Portal zuletzt genutzt hat.

Die Anmeldung gilt 90 Tage, `last_login` sagt deshalb wenig. Geschrieben wird
höchstens alle paar Minuten, damit nicht jeder Seitenaufruf die Datenbank belastet.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone

ABSTAND = timedelta(minutes=5)


def zuletzt_aktiv(get_response):
    def middleware(request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            jetzt = timezone.now()
            if user.zuletzt_aktiv is None or user.zuletzt_aktiv < jetzt - ABSTAND:
                try:
                    get_user_model().objects.filter(
                        Q(zuletzt_aktiv__isnull=True) | Q(zuletzt_aktiv__lt=jetzt - ABSTAND), pk=user.pk,
                    ).update(zuletzt_aktiv=jetzt)
                    user.zuletzt_aktiv = jetzt
                except DatabaseError:
                    pass   # die Statistik darf keine Seite verhindern
        return get_response(request)

    return middleware

"""Bucht fällige Termine einer Serie als Logbucheinträge (ohne Tachostand)."""
from datetime import date

from django.db import transaction

from .forms import zeitpunkt_am
from .models import Eintrag


@transaction.atomic
def buchen(serie, bis=None):
    bis = bis or date.today()
    n = 0
    for termin in serie.termine(bis):
        if serie.eintraege.filter(zeitpunkt__date=termin).exists():
            continue
        Eintrag.objects.create(fahrzeug=serie.fahrzeug, kategorie=serie.kategorie, zeitpunkt=zeitpunkt_am(termin),
                               kosten=serie.betrag, beschreibung=serie.beschreibung, serie=serie,
                               erfasst_von=serie.angelegt_von)
        n += 1
    return n

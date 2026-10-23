"""Schickt Erinnerungen per Mail, wenn eine Fälligkeit näher rückt.

    docker compose exec -T web python manage.py erinnerungen [--trocken] [--heute 2027-03-01]

Fällig ist eine Erinnerung ERINNERUNG_TAGE_VORHER Tage vor dem Datum oder ERINNERUNG_KM_VORHER km
vor dem Tachostand (geschätzt aus der Fahrleistung der letzten zwölf Monate). Jede Erinnerung
kommt einmal an alle Mitglieder der Familie, die Mails wünschen; ändert sich die Fälligkeit,
wieder neu. Täglich per Cron.
"""
from collections import defaultdict
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from auswertung.kennzahlen import faelligkeiten, kennzahlen
from fahrzeuge.models import Fahrzeug
from konten.models import Person
from logbuch.verbrauch import faelligkeit
from portal import mails


class Command(BaseCommand):
    help = "Erinnerungen per Mail verschicken"

    def add_arguments(self, parser):
        parser.add_argument("--trocken", action="store_true", help="nur anzeigen, nichts senden")
        parser.add_argument("--heute", type=date.fromisoformat, help="Stichtag (zum Testen)")

    def handle(self, trocken=False, heute=None, **opts):
        heute = heute or date.today()
        je_familie = defaultdict(list)
        for f in Fahrzeug.objects.filter(verkauf_datum__isnull=True).select_related("familie"):
            kz = kennzahlen(f)
            for fl in faelligkeiten(f, kz):
                fl = faelligkeit(fl.erinnerung, kz.tachostand, kz.km_pro_tag, heute)
                e = fl.erinnerung
                if e.mail_gesendet_am:
                    continue
                nach_tagen = fl.tage_rest is not None and fl.tage_rest <= settings.ERINNERUNG_TAGE_VORHER
                nach_km = fl.km_rest is not None and fl.km_rest <= settings.ERINNERUNG_KM_VORHER
                if nach_tagen or nach_km:
                    je_familie[f.familie_id].append((f, fl))
        gesendet = 0
        for familie_id, faellige in je_familie.items():
            empfaenger = Person.objects.filter(familie_id=familie_id, is_active=True, erinnerungen_per_mail=True)
            for person in empfaenger:
                self.stdout.write(f"{heute} {person.email}: " + ", ".join(f"{fl.erinnerung} ({f})" for f, fl in faellige))
                if not trocken:
                    mails.erinnerungen(person, faellige)
                    gesendet += 1
            if not trocken:
                for _f, fl in faellige:
                    fl.erinnerung.mail_gesendet_am = heute
                    fl.erinnerung.save(update_fields=["mail_gesendet_am"])
        self.stdout.write(f"{heute}: {gesendet} Mails")

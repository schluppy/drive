"""Importiert ein DriveNote-Backup für eine Person (in deren Familie).

    docker compose exec web python manage.py drivenote_import import/Drivenote_Backup.zip du@example.org

Ohne --zuordnung werden Fahrzeuge mit bekannter UUID oder gleichem Kennzeichen zugeordnet,
die übrigen neu angelegt. Die Oberfläche (/import/) zeigt die Zuordnung vorher an.
"""
from django.core.management.base import BaseCommand, CommandError

from importe import drivenote, uebernahme
from konten.models import Person


class Command(BaseCommand):
    help = "DriveNote-Backup importieren"

    def add_arguments(self, parser):
        parser.add_argument("datei")
        parser.add_argument("email", help="Person, deren Familie die Daten bekommt (wird „erfasst von“)")
        parser.add_argument("--zuordnung", nargs="*", default=[], metavar="NR=ZIEL",
                            help="z. B. 4=neu 2=aus 1=17 (17 = Fahrzeug-ID der Familie)")
        parser.add_argument("--trocken", action="store_true", help="nur anzeigen, was im Backup steht")

    def handle(self, datei, email, zuordnung, trocken, **opts):
        person = Person.objects.filter(email=email.strip().lower()).first()
        if person is None or person.familie is None:
            raise CommandError(f"{email}: keine Person mit Familie")
        try:
            backup = drivenote.lesen(datei)
        except (OSError, drivenote.BackupFehler) as e:
            raise CommandError(str(e)) from e
        wahl = uebernahme.vorschlag(backup, person.familie)
        for teil in zuordnung:
            nr, _, ziel = teil.partition("=")
            wahl[nr] = ziel
        for fz in drivenote.fahrzeuge(backup):
            self.stdout.write(f"  Fahrzeug {fz.nr}: {fz.name} {fz.felder['kennzeichen']} – "
                              f"{fz.eintraege} Einträge → {wahl.get(fz.nr)}")
        if trocken:
            return
        bericht = uebernahme.uebernehmen(backup, person, wahl)
        self.stdout.write(self.style.SUCCESS(
            f"Fahrzeuge neu: {len(bericht.fahrzeuge_neu)}, zugeordnet: {len(bericht.fahrzeuge_zugeordnet)}; "
            f"Einträge neu: {bericht.eintraege_neu}, aktualisiert: {bericht.eintraege_aktualisiert}, "
            f"doppelt: {bericht.eintraege_doppelt}; Erinnerungen neu: {bericht.erinnerungen_neu}, "
            f"aktualisiert: {bericht.erinnerungen_aktualisiert}"))
        for h in bericht.hinweise:
            self.stdout.write(self.style.WARNING(h))

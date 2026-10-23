"""Kennzahlen eines Fahrzeugs für Übersicht, Statistik und Vergleich – aus einer einzigen
Abfrage der Einträge, damit die Seiten auch bei vielen Jahren Logbuch schnell bleiben."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone

from logbuch import verbrauch as vb
from logbuch.models import Kategorieart


def eintraege_von(fahrzeug):
    return list(fahrzeug.eintraege.select_related("kategorie", "erfasst_von"))


@dataclass
class KraftstoffKennzahlen:
    nr: int
    name: str
    einheit: str
    abschnitte: list
    verbrauch: vb.Verbrauch
    fuellungen: list = field(default_factory=list)

    @property
    def kosten_gesamt(self):
        return sum((f.kosten for f in self.fuellungen), Decimal(0))

    @property
    def menge_gesamt(self):
        return sum((f.menge for f in self.fuellungen), Decimal(0))

    @property
    def kosten_je_km(self):
        """Alle Tankkosten durch die Strecke von der ersten bis zur letzten Tankfüllung (wie DriveNote)."""
        if len(self.fuellungen) < 2:
            return None
        km = self.fuellungen[-1].tachostand - self.fuellungen[0].tachostand
        return self.kosten_gesamt / km if km > 0 else None


@dataclass
class Kennzahlen:
    fahrzeug: object
    eintraege: list
    tachostand: int | None
    fahrleistung: int
    kosten_gesamt: Decimal
    kraftstoffe: list
    km_pro_tag: Decimal | None

    @property
    def kosten_je_km(self):
        return self.kosten_gesamt / self.fahrleistung if self.fahrleistung else None

    def kraftstoff(self, nr):
        return next((k for k in self.kraftstoffe if k.nr == nr), None)


def kennzahlen(fahrzeug, eintraege=None, jahr=None):
    """jahr=None: alles; sonst nur Kosten, Abschnitte und Fahrleistung dieses Jahres."""
    if eintraege is None:
        eintraege = eintraege_von(fahrzeug)
    im_jahr = [e for e in eintraege if jahr is None or timezone.localtime(e.zeitpunkt).year == jahr]
    kraftstoffe = []
    for nr, _wert, name, einheit in fahrzeug.kraftstoffe:
        fuellungen = vb.tankfuellungen(fahrzeug, nr, eintraege)
        abschnitte = vb.im_zeitraum(vb.abschnitte(fuellungen), jahr)
        kraftstoffe.append(KraftstoffKennzahlen(
            nr, name, einheit, abschnitte, vb.verbrauch(abschnitte),
            [f for f in fuellungen if jahr is None or timezone.localtime(f.zeitpunkt).year == jahr]))
    if jahr is None:
        fahrleistung = vb.fahrleistung(fahrzeug, eintraege)
    else:
        fahrleistung = vb.jahresfahrleistung(fahrzeug, eintraege).get(jahr, 0)
    return Kennzahlen(
        fahrzeug=fahrzeug, eintraege=eintraege,
        tachostand=vb.aktueller_tachostand(fahrzeug, eintraege),
        fahrleistung=fahrleistung,
        kosten_gesamt=sum((e.kosten for e in im_jahr), Decimal(0)),
        kraftstoffe=kraftstoffe,
        km_pro_tag=vb.km_pro_tag(fahrzeug, eintraege),
    )


def jahre(eintraege):
    return sorted({timezone.localtime(e.zeitpunkt).year for e in eintraege}, reverse=True)


def faelligkeiten(fahrzeug, kz, offene=None):
    """Offene Erinnerungen mit Restkilometern, Resttagen und Schätzung, die nächste zuerst."""
    if offene is None:
        offene = fahrzeug.erinnerungen.filter(erledigt_am__isnull=True).select_related("kategorie")
    liste = [vb.faelligkeit(e, kz.tachostand, kz.km_pro_tag) for e in offene]
    return sorted(liste, key=lambda f: (f.tage_bis is None, f.tage_bis if f.tage_bis is not None else 0))


def kosten_nach_kategorie(eintraege, jahr=None):
    """[(Kategorie, Anzahl, Summe)] absteigend nach Summe"""
    summen = {}
    for e in eintraege:
        if jahr is not None and timezone.localtime(e.zeitpunkt).year != jahr:
            continue
        if not e.kosten:
            continue
        k = summen.setdefault(e.kategorie_id, [e.kategorie, 0, Decimal(0)])
        k[1] += 1
        k[2] += e.kosten
    return sorted((tuple(v) for v in summen.values()), key=lambda t: -t[2])


def ist_tankfuellung(e):
    return e.kategorie.art == Kategorieart.TANKEN


def heute():
    return date.today()

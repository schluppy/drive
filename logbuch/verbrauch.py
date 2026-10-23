"""Verbrauch, Strecken und Schätzungen – die Fachlogik hinter Statistik und Vergleich.

Verbrauch wird von voller zu voller Tankfüllung gerechnet (ein *Abschnitt*):
Menge und Kosten aller Tankfüllungen nach der ersten vollen bis einschließlich der
nächsten vollen, geteilt durch die Strecke dazwischen. Teilfüllungen zählen zum
nächsten vollen Tank. „Vorherige Tankfüllung nicht erfasst“ beginnt eine neue Kette;
die Strecke davor zählt nicht.

Gesamt = Summe Menge / Summe Strecke aller Abschnitte, Aktuell = letzter Abschnitt,
BC = Bordcomputer-Werte gewichtet nach Strecke. So rechnet auch DriveNote
(geprüft am eigenen Backup: 10,395 / 11,104 / 9,646 l/100 km).
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Eintrag, Kategorieart

HUNDERT = Decimal(100)


@dataclass
class Abschnitt:
    von: Eintrag
    bis: Eintrag
    km: int
    menge: Decimal
    kosten: Decimal
    fuellungen: list = field(default_factory=list)

    @property
    def verbrauch(self):
        return self.menge / self.km * HUNDERT if self.km > 0 else None

    @property
    def kosten_je_km(self):
        return self.kosten / self.km if self.km > 0 else None

    @property
    def bc(self):
        return self.bis.bc_verbrauch

    @property
    def person(self):
        return self.bis.erfasst_von

    @property
    def datum(self):
        return timezone.localtime(self.bis.zeitpunkt).date()


def tankfuellungen(fahrzeug, nr=1, eintraege=None):
    """Tankfüllungen eines Kraftstoffs nach Tachostand (bei gleichem Stand nach Zeit)."""
    if eintraege is None:
        eintraege = fahrzeug.eintraege.select_related("kategorie", "erfasst_von")
    liste = [e for e in eintraege
             if e.kategorie.art == Kategorieart.TANKEN and e.kraftstoff_nr == nr
             and e.tachostand is not None and e.menge]
    liste.sort(key=lambda e: (e.tachostand, e.zeitpunkt, e.pk or 0))
    return liste


def abschnitte(fuellungen):
    ergebnis = []
    anker = None
    menge = kosten = Decimal(0)
    offen = []
    for f in fuellungen:
        if f.vorherige_fehlt:
            anker, menge, kosten, offen = (f if f.tank_voll else None), Decimal(0), Decimal(0), []
            continue
        if anker is None:
            if f.tank_voll:
                anker = f
            continue
        menge += f.menge
        kosten += f.kosten or 0
        offen.append(f)
        if f.tank_voll:
            km = f.tachostand - anker.tachostand
            if km > 0:
                ergebnis.append(Abschnitt(anker, f, km, menge, kosten, offen))
            anker, menge, kosten, offen = f, Decimal(0), Decimal(0), []
    return ergebnis


@dataclass
class Verbrauch:
    gesamt: Decimal | None
    aktuell: Decimal | None
    bc: Decimal | None
    km: int
    menge: Decimal
    kosten: Decimal
    anzahl: int

    @property
    def trend(self):
        """'hoch', 'runter' oder '' – Aktuell gegenüber Gesamt"""
        if self.gesamt is None or self.aktuell is None:
            return ""
        return "hoch" if self.aktuell > self.gesamt else "runter" if self.aktuell < self.gesamt else ""

    @property
    def kosten_je_km(self):
        return self.kosten / self.km if self.km else None

    @property
    def km_je_fuellung(self):
        return Decimal(self.km) / self.anzahl if self.anzahl else None


def verbrauch(liste):
    km = sum(a.km for a in liste)
    menge = sum((a.menge for a in liste), Decimal(0))
    kosten = sum((a.kosten for a in liste), Decimal(0))
    mit_bc = [a for a in liste if a.bc]
    bc_km = sum(a.km for a in mit_bc)
    return Verbrauch(
        gesamt=menge / km * HUNDERT if km else None,
        aktuell=liste[-1].verbrauch if liste else None,
        bc=sum((a.bc * a.km for a in mit_bc), Decimal(0)) / bc_km if bc_km else None,
        km=km, menge=menge, kosten=kosten, anzahl=len(liste),
    )


def im_zeitraum(liste, jahr=None):
    """Abschnitte, deren Tankfüllung am Ende im Jahr liegt (None = alle)."""
    if jahr is None:
        return liste
    return [a for a in liste if a.datum.year == jahr]


# --- Tachostand, Fahrleistung und Schätzungen --------------------------------

def mit_tachostand(eintraege):
    return sorted((e for e in eintraege if e.tachostand is not None), key=lambda e: (e.zeitpunkt, e.tachostand))


def aktueller_tachostand(fahrzeug, eintraege=None):
    if eintraege is None:
        eintraege = fahrzeug.eintraege.all()
    staende = [e.tachostand for e in eintraege if e.tachostand is not None]
    werte = staende + [fahrzeug.erwerb_km] if fahrzeug.erwerb_km is not None else staende
    return max(werte) if werte else None


def start_tachostand(fahrzeug, eintraege=None):
    if fahrzeug.erwerb_km is not None:
        return fahrzeug.erwerb_km
    if eintraege is None:
        eintraege = fahrzeug.eintraege.all()
    staende = [e.tachostand for e in eintraege if e.tachostand is not None]
    return min(staende) if staende else None


def fahrleistung(fahrzeug, eintraege=None):
    aktuell = aktueller_tachostand(fahrzeug, eintraege)
    start = start_tachostand(fahrzeug, eintraege)
    if aktuell is None or start is None:
        return 0
    return max(aktuell - start, 0)


def km_pro_tag(fahrzeug, eintraege=None, heute=None):
    """Durchschnitt der letzten 365 Tage (bei jüngeren Fahrzeugen seit dem ersten Eintrag)."""
    heute = heute or date.today()
    if eintraege is None:
        eintraege = fahrzeug.eintraege.all()
    liste = mit_tachostand(eintraege)
    if len(liste) < 2:
        return None
    seit = heute - timedelta(days=365)
    frueher = [e for e in liste if timezone.localtime(e.zeitpunkt).date() <= seit]
    basis = frueher[-1] if frueher else liste[0]
    letzter = max(liste, key=lambda e: e.tachostand)
    tage = (timezone.localtime(letzter.zeitpunkt).date() - timezone.localtime(basis.zeitpunkt).date()).days
    if tage <= 0:
        return None
    return Decimal(letzter.tachostand - basis.tachostand) / tage


def jahresfahrleistung(fahrzeug, eintraege=None):
    """{Jahr: km} – Tachostand am Jahresende minus Stand am Ende des Vorjahres (bzw. beim Kauf)."""
    liste = mit_tachostand(eintraege if eintraege is not None else fahrzeug.eintraege.all())
    if not liste:
        return {}
    hoechster = {}
    for e in liste:
        jahr = timezone.localtime(e.zeitpunkt).year
        hoechster[jahr] = max(hoechster.get(jahr, 0), e.tachostand)
    ergebnis = {}
    vorher = start_tachostand(fahrzeug, liste)
    for jahr in sorted(hoechster):
        stand = max(hoechster[jahr], vorher)
        ergebnis[jahr] = stand - vorher
        vorher = stand
    return ergebnis


@dataclass
class Faelligkeit:
    erinnerung: object
    km_rest: int | None = None
    tage_rest: int | None = None
    km_geschaetzt: Decimal | None = None
    datum_geschaetzt: date | None = None

    @property
    def tage_bis(self):
        """Tage bis zur Fälligkeit, ob nach Datum oder geschätzt nach km – das Frühere."""
        werte = [t for t in (self.tage_rest,
                             (self.datum_geschaetzt - date.today()).days if self.datum_geschaetzt else None)
                 if t is not None]
        return min(werte) if werte else None

    @property
    def ueberfaellig(self):
        return (self.km_rest is not None and self.km_rest < 0) or (self.tage_rest is not None and self.tage_rest < 0)


def faelligkeit(erinnerung, tachostand, kmpt, heute=None):
    heute = heute or date.today()
    f = Faelligkeit(erinnerung)
    if erinnerung.faellig_km is not None and tachostand is not None:
        f.km_rest = erinnerung.faellig_km - tachostand
        if kmpt and f.km_rest >= 0 and not erinnerung.faellig_am:
            f.datum_geschaetzt = heute + timedelta(days=int(f.km_rest / kmpt))
    if erinnerung.faellig_am:
        f.tage_rest = (erinnerung.faellig_am - heute).days
        if kmpt and tachostand is not None and not erinnerung.faellig_km and f.tage_rest >= 0:
            f.km_geschaetzt = tachostand + kmpt * f.tage_rest
    return f

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


def tachopunkte(eintraege):
    """[(Zeitpunkt, km)] aller Einträge mit Tachostand, nach Zeit. Wie DriveNote zählt nur der Stand am
    Ende eines Eintrags (bei Fahrten das Ziel). Ein Stand unter einem früheren zählt nicht, damit
    Tippfehler die Kurve nicht zurückdrehen."""
    roh = sorted((timezone.localtime(e.zeitpunkt), e.tachostand) for e in eintraege if e.tachostand is not None)
    punkte = []
    for zp, km in roh:
        if punkte and km < punkte[-1][1]:
            continue
        if punkte and punkte[-1][0] == zp:
            punkte[-1] = (zp, km)
        else:
            punkte.append((zp, km))
    return punkte


def _tage(von, bis):
    return Decimal((bis - von).total_seconds()) / 86400


def _anfang(tag_):
    """Mitternacht eines Tages in Ortszeit"""
    from datetime import datetime, time
    return timezone.make_aware(datetime.combine(tag_, time()))


def stand_am(punkte, zp):
    """Tachostand zu einem Zeitpunkt, linear zwischen den Einträgen; vor dem ersten None, nach dem letzten der letzte."""
    if not punkte or zp < punkte[0][0]:
        return None
    for (z0, k0), (z1, k1) in zip(punkte, punkte[1:]):
        if z0 <= zp <= z1:
            return Decimal(k0) + Decimal(k1 - k0) * _tage(z0, zp) / _tage(z0, z1)
    return Decimal(punkte[-1][1])


@dataclass
class Zeitraum:
    """Fahrleistung in einem Zeitraum (Jahr oder Monat), Grenzen interpoliert wie in DriveNote."""
    von: object
    bis: object
    km: Decimal
    erster: Decimal | None = None   # Tachostand am Anfang und Ende des Zeitraums
    letzter: Decimal | None = None

    @property
    def tage(self):
        return _tage(self.von, self.bis)

    @property
    def pro_tag(self):
        return self.km / self.tage if self.tage > 0 else None

    @property
    def pro_monat(self):
        return self.pro_tag * Decimal("30.4375") if self.pro_tag is not None else None


def fahrleistung_zeitraum(punkte, von, bis):
    """von, bis: Tage; von einschließlich, bis ausschließlich – beschnitten auf den Bereich mit Einträgen."""
    if not punkte:
        return None
    a, b = max(_anfang(von), punkte[0][0]), min(_anfang(bis), punkte[-1][0])
    if b < a:
        return None
    erster, letzter = stand_am(punkte, a), stand_am(punkte, b)
    return Zeitraum(a, b, letzter - erster, erster, letzter)


def jahresfahrleistung(fahrzeug, eintraege=None):
    """{Jahr: Zeitraum} von Jahresanfang zu Jahresanfang (bzw. erstem/letztem Eintrag)."""
    punkte = tachopunkte(eintraege if eintraege is not None else fahrzeug.eintraege.all())
    if not punkte:
        return {}
    ergebnis = {}
    for jahr in range(punkte[0][0].year, punkte[-1][0].year + 1):
        z = fahrleistung_zeitraum(punkte, date(jahr, 1, 1), date(jahr + 1, 1, 1))
        if z is not None:
            ergebnis[jahr] = z
    return ergebnis


def monatsfahrleistung(fahrzeug, jahr, eintraege=None):
    punkte = tachopunkte(eintraege if eintraege is not None else fahrzeug.eintraege.all())
    werte = []
    for m in range(1, 13):
        z = fahrleistung_zeitraum(punkte, date(jahr, m, 1), date(jahr + m // 12, m % 12 + 1, 1))
        werte.append(z.km if z else 0)
    return werte


@dataclass
class Fahrleistung:
    gesamt: Decimal
    pro_tag: Decimal | None
    prognose_jahr: int
    prognose: Decimal | None


def fahrleistung_kennzahlen(fahrzeug, eintraege=None, heute=None):
    """Gesamt und pro Tag über alle Einträge; Prognose fürs laufende Jahr = bisher + pro Tag × Rest des Jahres."""
    heute = heute or date.today()
    punkte = tachopunkte(eintraege if eintraege is not None else fahrzeug.eintraege.all())
    if len(punkte) < 2:
        return Fahrleistung(Decimal(0), None, heute.year, None)
    gesamt = Decimal(punkte[-1][1] - punkte[0][1])
    tage = _tage(punkte[0][0], punkte[-1][0])
    pro_tag = gesamt / tage if tage > 0 else None
    jahr = jahresfahrleistung(fahrzeug, eintraege).get(heute.year)
    prognose = None
    if pro_tag is not None and jahr is not None:
        ab = max(jahr.bis, _anfang(heute) if heute != date.today() else timezone.now())
        prognose = jahr.km + pro_tag * max(_tage(ab, _anfang(date(heute.year + 1, 1, 1))), 0)
    return Fahrleistung(gesamt, pro_tag, heute.year, prognose)


@dataclass
class Faelligkeit:
    erinnerung: object
    km_rest: int | None = None
    tage_rest: int | None = None
    km_geschaetzt: Decimal | None = None
    datum_geschaetzt: date | None = None
    tage_km: int | None = None  # Tage bis zum Tachostand, geschätzt aus der Fahrleistung

    @property
    def tage_bis(self):
        """Tage bis zur Fälligkeit, ob nach Datum oder geschätzt nach km – das Frühere."""
        werte = [t for t in (self.tage_rest, self.tage_km) if t is not None]
        return min(werte) if werte else None

    @property
    def zuerst(self):
        """'km' oder 'datum' – was zuerst eintritt (bei beidem gesetzt)."""
        if self.km_rest is None:
            return "datum" if self.tage_rest is not None else None
        if self.tage_rest is None:
            return "km"
        if self.tage_km is None:
            return "km" if self.km_rest < 0 else "datum"
        return "km" if self.tage_km < self.tage_rest else "datum"

    @property
    def ueberfaellig(self):
        return (self.km_rest is not None and self.km_rest < 0) or (self.tage_rest is not None and self.tage_rest < 0)


def faelligkeit(erinnerung, tachostand, kmpt, heute=None):
    heute = heute or date.today()
    f = Faelligkeit(erinnerung)
    if erinnerung.faellig_km is not None and tachostand is not None:
        f.km_rest = erinnerung.faellig_km - tachostand
        if kmpt:
            f.tage_km = int(f.km_rest / kmpt)
            if f.km_rest >= 0 and not erinnerung.faellig_am:
                f.datum_geschaetzt = heute + timedelta(days=f.tage_km)
    if erinnerung.faellig_am:
        f.tage_rest = (erinnerung.faellig_am - heute).days
        if kmpt and tachostand is not None and not erinnerung.faellig_km and f.tage_rest >= 0:
            f.km_geschaetzt = tachostand + kmpt * f.tage_rest
    return f

"""Logbuch: Tankfüllungen, Fahrten, Kosten, Serien und Erinnerungen.

Wie in DriveNote ist jede Zeile im Logbuch ein Eintrag mit Kategorie, Zeitpunkt,
Tachostand und Kosten. Die Art der Kategorie bestimmt, welche Felder dazukommen:
Tankfüllung (Kraftstoff, Menge, Füllstand, Bordcomputer) oder Fahrt (Start, Ziel).

Berechnet und nicht gespeichert: Preis je Liter, Strecke seit dem vorigen Eintrag,
Verbrauch (logbuch/verbrauch.py).
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Kategorieart(models.TextChoices):
    TANKEN = "tanken", "Tankfüllung"
    FAHRT = "fahrt", "Fahrt"
    KOSTEN = "kosten", "Kosten"


SYMBOLE = {
    "tanken": "⛽", "fahrt": "🛣️", "inspektion": "🔍", "reparatur": "🔧", "versicherung": "🛡️",
    "steuer": "§", "tuev": "✅", "reifen": "🛞", "waesche": "🧽", "oel": "🛢️", "additiv": "🧪",
    "camping": "⛺", "gas": "🔥", "parken": "🅿️", "maut": "🚧", "zubehoer": "🧰", "sonstiges": "📄",
}
SYMBOL_WAHL = [(k, f"{v} {k.capitalize()}") for k, v in SYMBOLE.items()]

# Kategorien jeder neuen Familie (wie in DriveNote); Tankfüllung und Fahrt sind geschützt
STANDARDKATEGORIEN = [
    ("Tankfüllung", Kategorieart.TANKEN, "tanken", "#4a90d9"),
    ("Fahrt", Kategorieart.FAHRT, "fahrt", "#4dd0e1"),
    ("Inspektion", Kategorieart.KOSTEN, "inspektion", "#ffb74d"),
    ("Reparatur", Kategorieart.KOSTEN, "reparatur", "#e57373"),
    ("Reifen", Kategorieart.KOSTEN, "reifen", "#a1887f"),
    ("Ölwechsel", Kategorieart.KOSTEN, "oel", "#fff176"),
    ("TÜV", Kategorieart.KOSTEN, "tuev", "#9575cd"),
    ("Versicherung", Kategorieart.KOSTEN, "versicherung", "#aed581"),
    ("Steuer", Kategorieart.KOSTEN, "steuer", "#4fc3f7"),
    ("Autowäsche", Kategorieart.KOSTEN, "waesche", "#7cb342"),
    ("Parken", Kategorieart.KOSTEN, "parken", "#90a4ae"),
    ("Sonstiges", Kategorieart.KOSTEN, "sonstiges", "#bdbdbd"),
]


class Kategorie(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="kategorien")
    name = models.CharField("Name", max_length=60)
    art = models.CharField("Art", max_length=10, choices=Kategorieart.choices, default=Kategorieart.KOSTEN)
    symbol = models.CharField("Symbol", max_length=20, choices=SYMBOL_WAHL, default="sonstiges")
    farbe = models.CharField("Farbe", max_length=7, default="#bdbdbd")
    geschuetzt = models.BooleanField(default=False, editable=False,
                                     help_text="Tankfüllung und Fahrt lassen sich nicht löschen")
    import_uuid = models.CharField(max_length=40, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"
        ordering = ["-geschuetzt", "name"]
        constraints = [models.UniqueConstraint(fields=["familie", "name"], name="kategorie_je_familie")]

    def __str__(self):
        return self.name

    @property
    def zeichen(self):
        return SYMBOLE.get(self.symbol, "📄")

    @classmethod
    def standard_anlegen(cls, familie):
        for name, art, symbol, farbe in STANDARDKATEGORIEN:
            cls.objects.get_or_create(familie=familie, name=name, defaults={
                "art": art, "symbol": symbol, "farbe": farbe, "geschuetzt": art != Kategorieart.KOSTEN})

    @classmethod
    def fuer(cls, familie, art):
        """Die (geschützte) Kategorie für Tankfüllungen bzw. Fahrten der Familie."""
        kat = cls.objects.filter(familie=familie, art=art).order_by("-geschuetzt", "pk").first()
        if kat is None:
            cls.standard_anlegen(familie)
            kat = cls.objects.filter(familie=familie, art=art).order_by("-geschuetzt", "pk").first()
        return kat


class Eintrag(models.Model):
    fahrzeug = models.ForeignKey("fahrzeuge.Fahrzeug", on_delete=models.CASCADE, related_name="eintraege")
    kategorie = models.ForeignKey(Kategorie, on_delete=models.PROTECT, related_name="eintraege")
    zeitpunkt = models.DateTimeField("Datum")
    tachostand = models.PositiveIntegerField("Tachostand", null=True, blank=True, help_text="km")
    kosten = models.DecimalField("Kosten", max_digits=10, decimal_places=2, default=0)
    ort = models.CharField("Ort", max_length=120, blank=True, help_text="Tankstelle, Werkstatt, Ziel …")
    beschreibung = models.TextField("Beschreibung", blank=True)
    erfasst_von = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="erfasst von", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="eintraege")

    # Tankfüllung
    kraftstoff_nr = models.PositiveSmallIntegerField("Kraftstoff", default=1, choices=[(1, "1"), (2, "2")])
    menge = models.DecimalField("Tankmenge", max_digits=8, decimal_places=3, null=True, blank=True)
    tank_voll = models.BooleanField("vollgetankt", default=True)
    vorherige_fehlt = models.BooleanField("vorherige Tankfüllung nicht erfasst", default=False,
                                          help_text="Strecke bis hierher zählt nicht zum Verbrauch")
    bc_verbrauch = models.DecimalField("Bordcomputer-Verbrauch", max_digits=5, decimal_places=2,
                                       null=True, blank=True, help_text="l/100 km laut Bordcomputer")

    # Fahrt
    start_zeitpunkt = models.DateTimeField("Start", null=True, blank=True)
    start_km = models.PositiveIntegerField("Tachostand Start", null=True, blank=True)
    start_ort = models.CharField("Startort", max_length=120, blank=True)

    serie = models.ForeignKey("Serie", on_delete=models.SET_NULL, null=True, blank=True, related_name="eintraege")
    import_uuid = models.CharField(max_length=40, blank=True, db_index=True, editable=False)
    angelegt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Logbucheintrag"
        verbose_name_plural = "Logbucheinträge"
        ordering = ["-zeitpunkt", "-tachostand", "-pk"]
        indexes = [models.Index(fields=["fahrzeug", "zeitpunkt"])]

    def __str__(self):
        return f"{self.kategorie} {timezone.localtime(self.zeitpunkt):%d.%m.%Y}"

    @property
    def ist_tanken(self):
        return self.kategorie.art == Kategorieart.TANKEN

    @property
    def ist_fahrt(self):
        return self.kategorie.art == Kategorieart.FAHRT

    @property
    def preis_je_einheit(self):
        if self.menge and self.kosten:
            return (self.kosten / self.menge).quantize(Decimal("0.001"), ROUND_HALF_UP)
        return None

    @property
    def fahrtstrecke(self):
        if self.start_km is not None and self.tachostand is not None:
            return self.tachostand - self.start_km
        return None

    @property
    def fahrtdauer(self):
        if self.start_zeitpunkt and self.zeitpunkt and self.zeitpunkt > self.start_zeitpunkt:
            return self.zeitpunkt - self.start_zeitpunkt
        return None


class Serie(models.Model):
    """Wiederkehrende Kosten (Versicherung, Steuer, Leasing …). `manage.py serien_buchen`
    legt fällige Einträge an."""

    fahrzeug = models.ForeignKey("fahrzeuge.Fahrzeug", on_delete=models.CASCADE, related_name="serien")
    kategorie = models.ForeignKey(Kategorie, on_delete=models.PROTECT, related_name="serien")
    betrag = models.DecimalField("Betrag", max_digits=10, decimal_places=2)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)
    intervall_monate = models.PositiveSmallIntegerField("alle … Monate", default=12,
                                                        choices=[(1, "monatlich"), (3, "vierteljährlich"),
                                                                 (6, "halbjährlich"), (12, "jährlich")])
    beginn = models.DateField("erste Buchung am")
    ende = models.DateField("letzte Buchung spätestens", null=True, blank=True)
    angelegt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Serie"
        verbose_name_plural = "Serien"
        ordering = ["beginn"]

    def __str__(self):
        return f"{self.kategorie} {self.get_intervall_monate_display()}"

    def termine(self, bis):
        """Alle Buchungstage von beginn bis `bis` (einschließlich)."""
        n = 0
        while True:
            monat = self.beginn.month - 1 + n * self.intervall_monate
            jahr = self.beginn.year + monat // 12
            monat = monat % 12 + 1
            tag = min(self.beginn.day, _letzter_tag(jahr, monat))
            termin = date(jahr, monat, tag)
            if termin > bis or (self.ende and termin > self.ende):
                return
            yield termin
            n += 1


def _letzter_tag(jahr, monat):
    naechster = date(jahr + monat // 12, monat % 12 + 1, 1)
    return (naechster - timedelta(days=1)).day


class Erinnerung(models.Model):
    """Fällig an einem Tag, bei einem Tachostand oder bei dem, was zuerst kommt.
    Wiederkehrende Erinnerungen legen beim Erledigen die nächste an."""

    fahrzeug = models.ForeignKey("fahrzeuge.Fahrzeug", on_delete=models.CASCADE, related_name="erinnerungen")
    kategorie = models.ForeignKey(Kategorie, on_delete=models.PROTECT, related_name="erinnerungen")
    notiz = models.CharField("Notiz", max_length=200, blank=True)
    faellig_am = models.DateField("fällig am", null=True, blank=True)
    faellig_km = models.PositiveIntegerField("fällig bei km", null=True, blank=True)
    wiederholen_monate = models.PositiveSmallIntegerField("wiederholen alle … Monate", null=True, blank=True)
    wiederholen_km = models.PositiveIntegerField("wiederholen alle … km", null=True, blank=True)
    erledigt_am = models.DateField("erledigt am", null=True, blank=True)
    mail_gesendet_am = models.DateField(null=True, blank=True, editable=False)
    import_uuid = models.CharField(max_length=40, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = "Erinnerung"
        verbose_name_plural = "Erinnerungen"
        ordering = ["erledigt_am", "faellig_am", "faellig_km"]

    def __str__(self):
        return f"{self.kategorie}: {self.notiz}" if self.notiz else str(self.kategorie)

    @property
    def wiederkehrend(self):
        return bool(self.wiederholen_monate or self.wiederholen_km)

    def naechste(self, erledigt_am, tachostand):
        """Die Folge-Erinnerung (ungespeichert) – ab dem Tag und Tachostand der Erledigung."""
        folge = Erinnerung(fahrzeug=self.fahrzeug, kategorie=self.kategorie, notiz=self.notiz,
                           wiederholen_monate=self.wiederholen_monate, wiederholen_km=self.wiederholen_km)
        if self.wiederholen_monate:
            basis = self.faellig_am or erledigt_am
            monat = basis.month - 1 + self.wiederholen_monate
            jahr, monat = basis.year + monat // 12, monat % 12 + 1
            folge.faellig_am = date(jahr, monat, min(basis.day, _letzter_tag(jahr, monat)))
        if self.wiederholen_km:
            folge.faellig_km = (self.faellig_km or tachostand or 0) + self.wiederholen_km
        return folge

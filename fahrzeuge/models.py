"""Fahrzeuge einer Familie.

Ein Fahrzeug gehört der Familie; alle Mitglieder sehen und bearbeiten es. Der Halter
ist die Person, die es hauptsächlich fährt – unter ihrem Namen erscheint es im Vergleich.
Bis zu zwei Kraftstoffe je Fahrzeug, z. B. Diesel und AdBlue. Wohnwagen und Anhänger
haben keinen Motor und tanken nicht; ihre Strecke ergibt sich aus den Fahrten.
"""
from datetime import date

from django.conf import settings
from django.db import models
from django.urls import reverse


class Kraftstoff(models.TextChoices):
    DIESEL = "diesel", "Diesel"
    SUPER = "super", "Super"
    SUPER_E10 = "e10", "Super E10"
    SUPER_PLUS = "superplus", "Super Plus"
    LPG = "lpg", "Autogas (LPG)"
    CNG = "cng", "Erdgas (CNG)"
    STROM = "strom", "Strom"
    ADBLUE = "adblue", "AdBlue"
    WASSERSTOFF = "h2", "Wasserstoff"


EINHEIT = {Kraftstoff.STROM: "kWh", Kraftstoff.CNG: "kg", Kraftstoff.WASSERSTOFF: "kg"}


def einheit_von(kraftstoff):
    return EINHEIT.get(kraftstoff, "l")


class Fahrzeugart(models.TextChoices):
    PKW = "pkw", "Pkw"
    MOTORRAD = "motorrad", "Motorrad"
    TRANSPORTER = "transporter", "Transporter"
    WOHNMOBIL = "wohnmobil", "Wohnmobil"
    WOHNWAGEN = "wohnwagen", "Wohnwagen"
    ANHAENGER = "anhaenger", "Anhänger"


OHNE_MOTOR = (Fahrzeugart.WOHNWAGEN, Fahrzeugart.ANHAENGER)


def foto_pfad(instanz, dateiname):
    endung = dateiname.rsplit(".", 1)[-1].lower() if "." in dateiname else "jpg"
    return f"fahrzeuge/{instanz.familie_id}/{instanz.pk or 'neu'}-{date.today():%Y%m%d}.{endung}"


class Fahrzeug(models.Model):
    familie = models.ForeignKey("konten.Familie", on_delete=models.CASCADE, related_name="fahrzeuge")
    halter = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Halter / Hauptfahrer",
                               on_delete=models.SET_NULL, null=True, blank=True, related_name="fahrzeuge",
                               help_text="unter diesem Namen erscheint das Fahrzeug im Vergleich")
    art = models.CharField("Art", max_length=12, choices=Fahrzeugart.choices, default=Fahrzeugart.PKW)
    hersteller = models.CharField("Hersteller", max_length=60)
    modell = models.CharField("Modell", max_length=80, blank=True)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True, help_text="z. B. Farbe")
    kennzeichen = models.CharField("Kennzeichen", max_length=20, blank=True)
    motorisierung = models.CharField("Motorisierung", max_length=40, blank=True, help_text="z. B. 185 PS")
    versicherung = models.CharField("Versicherung", max_length=80, blank=True)
    fin = models.CharField("Fahrzeug-Ident.-Nr.", max_length=30, blank=True)

    kraftstoff = models.CharField("Kraftstoff", max_length=10, choices=Kraftstoff.choices, blank=True,
                                  help_text="leer bei Wohnwagen und Anhängern")
    tankvolumen = models.DecimalField("Tankvolumen", max_digits=6, decimal_places=1, null=True, blank=True,
                                      help_text="Liter bzw. kWh")
    kraftstoff2 = models.CharField("Zweiter Kraftstoff", max_length=10, choices=Kraftstoff.choices, blank=True,
                                   help_text="z. B. AdBlue")
    tankvolumen2 = models.DecimalField("Tankvolumen (zweiter Kraftstoff)", max_digits=6, decimal_places=1,
                                       null=True, blank=True)

    hergestellt_am = models.DateField("Hergestellt am", null=True, blank=True)
    erstzulassung = models.DateField("Erstzulassung", null=True, blank=True)
    erwerb_datum = models.DateField("Gekauft am", null=True, blank=True)
    erwerb_km = models.PositiveIntegerField("Tachostand beim Kauf", null=True, blank=True)
    erwerb_preis = models.DecimalField("Kaufpreis", max_digits=10, decimal_places=2, null=True, blank=True)
    verkauf_datum = models.DateField("Verkauft am", null=True, blank=True)
    verkauf_km = models.PositiveIntegerField("Tachostand beim Verkauf", null=True, blank=True)
    verkauf_preis = models.DecimalField("Verkaufspreis", max_digits=10, decimal_places=2, null=True, blank=True)

    foto = models.ImageField("Foto", upload_to=foto_pfad, blank=True)
    im_vergleich = models.BooleanField("im Familienvergleich", default=True,
                                       help_text="aus = erscheint nicht in der Bestenliste")
    import_uuid = models.CharField(max_length=40, blank=True, db_index=True, editable=False)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fahrzeug"
        verbose_name_plural = "Fahrzeuge"
        ordering = ["verkauf_datum", "hersteller", "modell"]

    def __str__(self):
        return f"{self.hersteller} {self.modell}".strip()

    def get_absolute_url(self):
        return reverse("fahrzeuge:uebersicht", args=[self.pk])

    @property
    def verkauft(self):
        return self.verkauf_datum is not None

    @property
    def ohne_motor(self):
        """Wohnwagen und Anhänger: kein Kraftstoff, Strecke nur aus Fahrten"""
        return self.art in OHNE_MOTOR

    @property
    def kraftstoffe(self):
        """[(Nummer, Kraftstoff, Bezeichnung, Einheit)] – Nummer 1 oder 2 wie im Logbuch"""
        liste = []
        if self.kraftstoff:
            liste.append((1, self.kraftstoff, Kraftstoff(self.kraftstoff).label, einheit_von(self.kraftstoff)))
        if self.kraftstoff2:
            liste.append((2, self.kraftstoff2, Kraftstoff(self.kraftstoff2).label, einheit_von(self.kraftstoff2)))
        return liste

    def kraftstoff_name(self, nummer):
        wert = self.kraftstoff2 if nummer == 2 else self.kraftstoff
        return Kraftstoff(wert).label if wert else ""

    def einheit(self, nummer=1):
        return einheit_von(self.kraftstoff2 if nummer == 2 else self.kraftstoff)

    @property
    def einheit2(self):
        return self.einheit(2)

    def tankvolumen_von(self, nummer):
        return self.tankvolumen2 if nummer == 2 else self.tankvolumen

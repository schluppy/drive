"""Formulare für Tankfüllung, Fahrt, Logbucheintrag, Serie, Erinnerung und Kategorie."""
from decimal import ROUND_HALF_UP, Decimal

from django import forms
from django.utils import timezone

from fahrzeuge.forms import DatumFeld, _dezimal

from .models import Eintrag, Erinnerung, Kategorie, Kategorieart, Serie


class ZeitFeld(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class EintragBasis(forms.ModelForm):
    """Gemeinsam: Fahrzeug steht fest, Plausibilität Tachostand ↔ Datum."""

    trotzdem = forms.BooleanField(label="Trotzdem speichern", required=False,
                                  help_text="Tachostand und Datum passen nicht zu den übrigen Einträgen")

    def __init__(self, *args, fahrzeug, **kwargs):
        self.fahrzeug = fahrzeug
        super().__init__(*args, **kwargs)
        if "zeitpunkt" in self.fields:
            self.fields["zeitpunkt"].widget = ZeitFeld()
            self.fields["zeitpunkt"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
            if not self.instance.pk and not self.initial.get("zeitpunkt"):
                self.initial["zeitpunkt"] = timezone.localtime().replace(second=0, microsecond=0)
            elif self.instance.pk:
                self.initial["zeitpunkt"] = timezone.localtime(self.instance.zeitpunkt)
        for name in ("tachostand", "start_km"):
            if name in self.fields:
                self.fields[name].widget.attrs["inputmode"] = "numeric"
        if "kosten" in self.fields:
            _dezimal(self.fields["kosten"])
        if "beschreibung" in self.fields:
            self.fields["beschreibung"].widget = forms.Textarea(attrs={"rows": 2})
        self.unplausibel = []

    def _pruefen(self, zeitpunkt, tachostand):
        """Einträge, die mit Datum und Tachostand nicht zusammenpassen (früher mit mehr km
        oder später mit weniger km)."""
        if zeitpunkt is None or tachostand is None:
            return []
        qs = self.fahrzeug.eintraege.exclude(pk=self.instance.pk).filter(tachostand__isnull=False)
        frueher = qs.filter(zeitpunkt__lt=zeitpunkt, tachostand__gt=tachostand).order_by("-tachostand").first()
        spaeter = qs.filter(zeitpunkt__gt=zeitpunkt, tachostand__lt=tachostand).order_by("tachostand").first()
        return [e for e in (frueher, spaeter) if e]

    def clean(self):
        daten = super().clean()
        self.unplausibel = self._pruefen(daten.get("zeitpunkt"), daten.get("tachostand"))
        if self.unplausibel and not daten.get("trotzdem"):
            texte = [f"{timezone.localtime(e.zeitpunkt):%d.%m.%Y} mit {e.tachostand:,} km".replace(",", ".")
                     for e in self.unplausibel]
            raise forms.ValidationError(
                "Tachostand und Datum passen nicht zu den vorhandenen Einträgen ("
                + ", ".join(texte) + "). Bitte prüfen oder „Trotzdem speichern“ ankreuzen.")
        return daten

    def save(self, commit=True):
        eintrag = super().save(commit=False)
        eintrag.fahrzeug = self.fahrzeug
        if commit:
            eintrag.save()
        return eintrag


class TankenForm(EintragBasis):
    preis = forms.DecimalField(label="Preis pro Liter", required=False, max_digits=7, decimal_places=3)

    class Meta:
        model = Eintrag
        fields = ["kraftstoff_nr", "tachostand", "zeitpunkt", "kosten", "preis", "menge", "tank_voll",
                  "vorherige_fehlt", "bc_verbrauch", "ort", "beschreibung"]
        labels = {"kosten": "Gesamtpreis", "ort": "Tankstelle"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        f = self.fahrzeug
        self.fields["kraftstoff_nr"] = forms.TypedChoiceField(
            label="Kraftstoff", coerce=int, widget=forms.RadioSelect,
            choices=[(nr, name) for nr, _w, name, _e in f.kraftstoffe] or [(1, "Kraftstoff")],
            initial=self.instance.kraftstoff_nr or 1)
        self.fields["tachostand"].required = True
        self.fields["menge"].required = False   # lässt sich aus Gesamtpreis und Preis pro Liter rechnen
        einheit = f.einheit(self.instance.kraftstoff_nr or 1)
        self.fields["menge"].label = f"Tankmenge ({einheit})"
        self.fields["preis"].label = f"Preis pro {'Liter' if einheit == 'l' else einheit}"
        _dezimal(self.fields["menge"])
        _dezimal(self.fields["preis"])
        _dezimal(self.fields["bc_verbrauch"])
        self.fields["kosten"].required = False
        if self.instance.pk and self.instance.preis_je_einheit:
            self.initial["preis"] = self.instance.preis_je_einheit

    def clean(self):
        daten = super().clean()
        kosten, preis, menge = daten.get("kosten"), daten.get("preis"), daten.get("menge")
        # zwei von drei reichen: Gesamtpreis, Preis pro Liter, Menge
        if not kosten and preis and menge:
            daten["kosten"] = (preis * menge).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if menge is None and kosten and preis:
            daten["menge"] = (kosten / preis).quantize(Decimal("0.001"), ROUND_HALF_UP)
        if not daten.get("menge"):
            self.add_error("menge", "Bitte die Tankmenge angeben (oder Gesamtpreis und Preis pro Liter).")
        if daten.get("kosten") is None:
            daten["kosten"] = Decimal(0)
        return daten


class FahrtForm(EintragBasis):
    class Meta:
        model = Eintrag
        fields = ["start_zeitpunkt", "start_km", "start_ort", "zeitpunkt", "tachostand", "ort", "kosten",
                  "beschreibung"]
        labels = {"zeitpunkt": "Ankunft", "tachostand": "Tachostand Ziel", "ort": "Ziel"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_zeitpunkt"].widget = ZeitFeld()
        self.fields["start_zeitpunkt"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        if self.instance.pk and self.instance.start_zeitpunkt:
            self.initial["start_zeitpunkt"] = timezone.localtime(self.instance.start_zeitpunkt)
        self.fields["tachostand"].required = True
        self.fields["kosten"].required = False

    def clean(self):
        daten = super().clean()
        if daten.get("start_km") is not None and daten.get("tachostand") is not None \
                and daten["start_km"] > daten["tachostand"]:
            self.add_error("tachostand", "Der Tachostand am Ziel ist kleiner als am Start.")
        if daten.get("start_zeitpunkt") and daten.get("zeitpunkt") and daten["start_zeitpunkt"] > daten["zeitpunkt"]:
            self.add_error("zeitpunkt", "Die Ankunft liegt vor dem Start.")
        if daten.get("kosten") is None:
            daten["kosten"] = Decimal(0)
        return daten

    def _pruefen(self, zeitpunkt, tachostand):
        start = self.cleaned_data.get("start_km")
        # Einträge während der Fahrt (z. B. Tanken unterwegs) sind keine Unstimmigkeit
        return [e for e in super()._pruefen(zeitpunkt, tachostand)
                if not (start is not None and start <= e.tachostand <= tachostand)]


class KostenForm(EintragBasis):
    class Meta:
        model = Eintrag
        fields = ["kategorie", "zeitpunkt", "tachostand", "kosten", "ort", "beschreibung"]
        labels = {"ort": "Ort / Werkstatt"}

    def __init__(self, *args, kategorien, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = kategorien.filter(art=Kategorieart.KOSTEN)
        self.fields["kategorie"].empty_label = None


class SerieForm(forms.ModelForm):
    class Meta:
        model = Serie
        fields = ["kategorie", "betrag", "intervall_monate", "beginn", "ende", "beschreibung"]
        widgets = {"beginn": DatumFeld(), "ende": DatumFeld()}

    def __init__(self, *args, kategorien, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = kategorien.filter(art=Kategorieart.KOSTEN)
        self.fields["kategorie"].empty_label = None
        _dezimal(self.fields["betrag"])


class ErinnerungForm(forms.ModelForm):
    class Meta:
        model = Erinnerung
        fields = ["kategorie", "notiz", "faellig_am", "faellig_km", "wiederholen_monate", "wiederholen_km"]
        widgets = {"faellig_am": DatumFeld()}

    def __init__(self, *args, kategorien, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kategorie"].queryset = kategorien.filter(art=Kategorieart.KOSTEN)
        self.fields["kategorie"].empty_label = None
        for name in ("faellig_km", "wiederholen_km", "wiederholen_monate"):
            self.fields[name].widget.attrs["inputmode"] = "numeric"
        self.fields["wiederholen_monate"].help_text = "z. B. 24 für den TÜV"

    def clean(self):
        daten = super().clean()
        if not daten.get("faellig_am") and daten.get("faellig_km") is None:
            raise forms.ValidationError("Bitte ein Datum, einen Tachostand oder beides angeben.")
        return daten


class KategorieForm(forms.ModelForm):
    class Meta:
        model = Kategorie
        fields = ["name", "symbol", "farbe"]
        widgets = {"farbe": forms.TextInput(attrs={"type": "color"})}


class ErledigtForm(forms.Form):
    """Erinnerung erledigen; optional gleich einen Logbucheintrag mit Kosten anlegen."""
    datum = forms.DateField(label="Erledigt am", widget=DatumFeld())
    tachostand = forms.IntegerField(label="Tachostand", required=False, min_value=0)
    kosten = forms.DecimalField(label="Kosten", required=False, max_digits=10, decimal_places=2,
                                help_text="mit Kosten wird ein Logbucheintrag angelegt")
    ort = forms.CharField(label="Ort / Werkstatt", required=False, max_length=120)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tachostand"].widget.attrs["inputmode"] = "numeric"
        _dezimal(self.fields["kosten"])


def zeitpunkt_am(datum):
    """Datum → Zeitpunkt 12:00 Uhr (für Einträge ohne Uhrzeit)."""
    from datetime import datetime, time
    return timezone.make_aware(datetime.combine(datum, time(12))) if datum else None


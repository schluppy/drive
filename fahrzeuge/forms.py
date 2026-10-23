from django import forms

from konten.models import Person

from .models import OHNE_MOTOR, Fahrzeug


def _dezimal(feld):
    """Dezimalfeld mit Komma: Textfeld mit Zahlentastatur, Eingabe „90,00“ oder „90.00“."""
    feld.localize = True
    feld.widget = forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"})
    feld.widget.is_localized = True


class DatumFeld(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class FahrzeugForm(forms.ModelForm):
    class Meta:
        model = Fahrzeug
        fields = ["art", "hersteller", "modell", "beschreibung", "kennzeichen", "halter", "motorisierung",
                  "versicherung", "fin", "kraftstoff", "tankvolumen", "kraftstoff2", "tankvolumen2",
                  "hergestellt_am", "erstzulassung", "erwerb_datum", "erwerb_km", "erwerb_preis",
                  "verkauf_datum", "verkauf_km", "verkauf_preis", "foto", "im_vergleich"]
        widgets = {f: DatumFeld() for f in ["hergestellt_am", "erstzulassung", "erwerb_datum", "verkauf_datum"]}

    def __init__(self, *args, familie, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["halter"].queryset = Person.objects.filter(familie=familie, is_active=True)
        self.fields["foto"].widget = forms.ClearableFileInput(attrs={"accept": "image/*"})
        for name in ["erwerb_km", "verkauf_km"]:
            self.fields[name].widget.attrs["inputmode"] = "numeric"
        for name in ["tankvolumen", "tankvolumen2", "erwerb_preis", "verkauf_preis"]:
            _dezimal(self.fields[name])

    def clean(self):
        daten = super().clean()
        ohne_motor = daten.get("art") in OHNE_MOTOR
        if not ohne_motor and not daten.get("kraftstoff"):
            self.add_error("kraftstoff", "Bitte den Kraftstoff angeben.")
        if ohne_motor:
            daten["kraftstoff"] = daten["kraftstoff2"] = ""
        if daten.get("kraftstoff2") and daten.get("kraftstoff2") == daten.get("kraftstoff"):
            self.add_error("kraftstoff2", "Der zweite Kraftstoff muss sich vom ersten unterscheiden.")
        return daten

    def clean_foto(self):
        foto = self.cleaned_data.get("foto")
        if foto and hasattr(foto, "size") and foto.size > 15 * 1024 * 1024:
            raise forms.ValidationError("Das Foto ist größer als 15 MB.")
        return foto

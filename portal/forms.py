from django import forms

from konten.models import Person


class EinladungForm(forms.Form):
    name = forms.CharField(label="Name", max_length=150)
    email = forms.EmailField(label="E-Mail-Adresse")


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ["name", "farbe", "erinnerungen_per_mail"]
        widgets = {"farbe": forms.TextInput(attrs={"type": "color"})}
        help_texts = {"farbe": "Farbe im Familienvergleich"}

"""Ortsangaben (bisher Text) werden zu Orten je Familie; gleiche Namen (ohne Rücksicht auf
Leerzeichen und Groß-/Kleinschreibung) werden ein Ort."""
import django.db.models.deletion
from django.db import migrations, models


def texte_zu_orten(apps, schema_editor):
    Ort = apps.get_model("logbuch", "Ort")
    Eintrag = apps.get_model("logbuch", "Eintrag")
    cache = {}

    def holen(familie_id, text):
        name = " ".join((text or "").split())[:120]
        if not name:
            return None
        schluessel = (familie_id, name.lower())
        if schluessel not in cache:
            cache[schluessel] = Ort.objects.create(familie_id=familie_id, name=name)
        return cache[schluessel]

    for e in Eintrag.objects.select_related("fahrzeug").order_by("zeitpunkt"):
        e.ort_neu = holen(e.fahrzeug.familie_id, e.ort)
        e.start_ort_neu = holen(e.fahrzeug.familie_id, e.start_ort)
        if e.ort_neu or e.start_ort_neu:
            e.save(update_fields=["ort_neu", "start_ort_neu"])


class Migration(migrations.Migration):
    dependencies = [
        ("konten", "0001_initial"),
        ("logbuch", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Ort",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, verbose_name="Name")),
                ("familie", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orte",
                                              to="konten.familie")),
            ],
            options={"verbose_name": "Ort", "verbose_name_plural": "Orte", "ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="ort", constraint=models.UniqueConstraint(fields=("familie", "name"), name="ort_je_familie")),
        migrations.AddField(model_name="eintrag", name="ort_neu", field=models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="logbuch.ort")),
        migrations.AddField(model_name="eintrag", name="start_ort_neu", field=models.ForeignKey(
            null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="logbuch.ort")),
        migrations.RunPython(texte_zu_orten, migrations.RunPython.noop),
        migrations.RemoveField(model_name="eintrag", name="ort"),
        migrations.RemoveField(model_name="eintrag", name="start_ort"),
        migrations.RenameField(model_name="eintrag", old_name="ort_neu", new_name="ort"),
        migrations.RenameField(model_name="eintrag", old_name="start_ort_neu", new_name="start_ort"),
        migrations.AlterField(model_name="eintrag", name="ort", field=models.ForeignKey(
            blank=True, help_text="Tankstelle, Werkstatt, Ziel …", null=True,
            on_delete=django.db.models.deletion.SET_NULL, related_name="eintraege", to="logbuch.ort",
            verbose_name="Ort")),
        migrations.AlterField(model_name="eintrag", name="start_ort", field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="fahrtstarts",
            to="logbuch.ort", verbose_name="Startort")),
    ]

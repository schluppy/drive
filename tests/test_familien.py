"""Trennung der Familien: fremde Fahrzeuge, Einträge, Kategorien und Fotos sind nicht erreichbar."""
from django.test import TestCase
from django.urls import reverse

from logbuch.models import Eintrag, Erinnerung, Kategorie, Serie

from .hilfen import fahrzeug, familie_mit_person, tanken


class FamilienTest(TestCase):
    def setUp(self):
        self.familie_a, self.a = familie_mit_person("A", "a@example.org")
        self.familie_b, self.b = familie_mit_person("B", "b@example.org")
        self.fa = fahrzeug(self.familie_a, self.a, modell="Eigenes")
        self.fb = fahrzeug(self.familie_b, self.b, modell="Fremdes")
        tanken(self.fb, "01.01.2026", 1000, 50, 80, person=self.b)
        self.eb = tanken(self.fb, "05.01.2026", 2000, 60, 100, person=self.b)
        self.kb = Kategorie.objects.get(familie=self.familie_b, name="TÜV")
        self.erb = Erinnerung.objects.create(fahrzeug=self.fb, kategorie=self.kb, faellig_km=5000)
        self.sb = Serie.objects.create(fahrzeug=self.fb, kategorie=self.kb, betrag=10, beginn="2026-01-01")
        from logbuch.models import Ort
        self.ob = Ort.objects.create(familie=self.familie_b, name="Geheimer Ort")
        self.client.force_login(self.a)

    def test_fremde_seiten_404(self):
        f = self.fb.pk
        urls = [
            reverse("fahrzeuge:uebersicht", args=[f]), reverse("fahrzeuge:bearbeiten", args=[f]),
            reverse("fahrzeuge:foto", args=[f]), reverse("logbuch:liste", args=[f]),
            reverse("logbuch:neu", args=[f, "tanken"]), reverse("logbuch:serien", args=[f]),
            reverse("logbuch:serie", args=[f, self.sb.pk]), reverse("logbuch:erinnerungen", args=[f]),
            reverse("logbuch:erinnerung", args=[f, self.erb.pk]), reverse("logbuch:erledigt", args=[f, self.erb.pk]),
            reverse("logbuch:bearbeiten", args=[self.eb.pk]), reverse("logbuch:kategorie", args=[self.kb.pk]),
            reverse("logbuch:ort", args=[self.ob.pk]),
            reverse("auswertung:statistik", args=[f]), reverse("auswertung:kosten", args=[f]),
            # Erinnerung/Serie der anderen Familie unter dem eigenen Fahrzeug
            reverse("logbuch:erinnerung", args=[self.fa.pk, self.erb.pk]),
            reverse("logbuch:serie", args=[self.fa.pk, self.sb.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_fremdes_loeschen_404(self):
        self.assertEqual(self.client.post(reverse("logbuch:loeschen", args=[self.eb.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("fahrzeuge:loeschen", args=[self.fb.pk]),
                                          {"bestaetigt": str(self.fb)}).status_code, 404)
        self.assertTrue(Eintrag.objects.filter(pk=self.eb.pk).exists())

    def test_vergleich_und_start_nur_eigene(self):
        for url in (reverse("auswertung:vergleich"), reverse("portal:start"), reverse("fahrzeuge:liste"),
                    reverse("logbuch:orte"), reverse("logbuch:neu", args=[self.fa.pk, "kosten"])):
            inhalt = self.client.get(url).content.decode()
            self.assertNotIn("Fremdes", inhalt, url)
            self.assertNotIn("Geheimer Ort", inhalt, url)

    def test_fremde_kategorie_nicht_waehlbar(self):
        antwort = self.client.post(reverse("logbuch:neu", args=[self.fa.pk, "kosten"]), {
            "kategorie": self.kb.pk, "zeitpunkt": "2026-01-01T10:00", "kosten": "5"})
        self.assertEqual(antwort.status_code, 200)
        self.assertIn("kategorie", antwort.context["form"].errors)
        self.assertFalse(Eintrag.objects.filter(fahrzeug=self.fa).exists())

    def test_einladung_in_fremde_familie_abgelehnt(self):
        antwort = self.client.post(reverse("portal:familie"), {"name": "B", "email": "b@example.org"})
        self.assertIn("email", antwort.context["form"].errors)
        self.b.refresh_from_db()
        self.assertEqual(self.b.familie, self.familie_b)

    def test_ohne_familie(self):
        from konten.models import Person
        p = Person.objects.create_user("c@example.org", "Ohne")
        self.client.force_login(p)
        self.assertEqual(self.client.get(reverse("logbuch:liste", args=[self.fa.pk])).status_code, 403)

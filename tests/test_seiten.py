from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from konten.models import MagicLinkToken, Person
from logbuch.models import Eintrag, Erinnerung, Kategorie, Serie

from .hilfen import fahrzeug, familie_mit_person, tanken


@override_settings(MEDIA_ROOT="/tmp/drive-test-media")
class SeitenTest(TestCase):
    def setUp(self):
        self.familie, self.a = familie_mit_person("Muster", "a@example.org")
        self.b = Person.objects.create_user("b@example.org", "Bea Muster", familie=self.familie)
        self.f = fahrzeug(self.familie, self.a, kraftstoff2="adblue", kennzeichen="AB-C 1")
        self.g = fahrzeug(self.familie, self.b, modell="Klein", kraftstoff="e10")
        for f, p, l in ((self.f, self.a, 60), (self.g, self.b, 40)):
            tanken(f, "01.01.2026", 1000, 50, 80, person=p)
            tanken(f, "05.02.2026", 1800, l, 100, person=p, bc=6)
            tanken(f, "05.03.2026", 2500, l - 5, 90, person=p)
        self.client.force_login(self.a)

    def test_alle_seiten(self):
        f = self.f.pk
        e = self.f.eintraege.first()
        er = Erinnerung.objects.create(fahrzeug=self.f, kategorie=Kategorie.objects.get(familie=self.familie,
                                       name="TÜV"), faellig_am=date.today() + timedelta(days=30), wiederholen_monate=24)
        for url in ["/", "/familie/", "/profil/", "/datenschutz/", "/manifest.webmanifest", "/import/",
                    reverse("fahrzeuge:liste"), reverse("fahrzeuge:neu"), reverse("fahrzeuge:uebersicht", args=[f]),
                    reverse("fahrzeuge:bearbeiten", args=[f]), reverse("logbuch:liste", args=[f]),
                    reverse("logbuch:liste", args=[f]) + "?jahr=2026",
                    reverse("logbuch:neu", args=[f, "tanken"]), reverse("logbuch:neu", args=[f, "fahrt"]),
                    reverse("logbuch:neu", args=[f, "kosten"]), reverse("logbuch:bearbeiten", args=[e.pk]),
                    reverse("logbuch:serien", args=[f]), reverse("logbuch:serie_neu", args=[f]),
                    reverse("logbuch:erinnerungen", args=[f]), reverse("logbuch:erinnerung_neu", args=[f]),
                    reverse("logbuch:erledigt", args=[f, er.pk]), reverse("logbuch:kategorien"),
                    reverse("logbuch:kategorie_neu"), reverse("logbuch:orte"), reverse("auswertung:statistik", args=[f]),
                    reverse("auswertung:statistik", args=[f]) + "?jahr=2026", reverse("auswertung:kosten", args=[f]),
                    reverse("auswertung:kosten", args=[f]) + "?jahr=2026", reverse("auswertung:vergleich"),
                    reverse("auswertung:vergleich") + "?jahr=2026"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_statistik_gesamtsumme_und_bereiche(self):
        antwort = self.client.get(reverse("auswertung:statistik", args=[self.f.pk]))
        diesel = antwort.context["kraftstoffe"][0]
        self.assertEqual(diesel["summe"]["menge"], sum(z["menge"] for z in diesel["je_jahr"]))
        self.assertContains(antwort, 'href="#fahrleistung"')
        self.assertContains(antwort, 'id="fahrleistung"')
        self.assertContains(antwort, 'href="#top"')
        jahr = self.client.get(reverse("auswertung:statistik", args=[self.f.pk]) + "?jahr=2026")
        self.assertIsNone(jahr.context["kraftstoffe"][0]["summe"])

    def test_plus_nur_im_logbuch(self):
        f = self.f.pk
        self.assertContains(self.client.get(reverse("logbuch:liste", args=[f])), 'class="plus"')
        for url in (reverse("auswertung:statistik", args=[f]), reverse("fahrzeuge:uebersicht", args=[f]),
                    reverse("logbuch:erinnerungen", args=[f])):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), 'class="plus"')

    def test_vergleich_rangfolge(self):
        antwort = self.client.get(reverse("auswertung:vergleich"))
        zeilen = antwort.context["zeilen"]
        self.assertEqual([z["fahrzeug"] for z in zeilen], [self.g, self.f])   # Klein verbraucht weniger
        self.assertEqual(antwort.context["beste"]["sparsam"]["fahrzeug"], self.g)
        personen = antwort.context["personen"]
        self.assertEqual([p["person"] for p in personen], [self.b, self.a])
        self.assertEqual(personen[0]["weiteste"].km, 800)

    def test_tanken_rechnet_menge(self):
        antwort = self.client.post(reverse("logbuch:neu", args=[self.f.pk, "tanken"]), {
            "kraftstoff_nr": "1", "tachostand": "3100", "zeitpunkt": "2026-03-20T08:00", "kosten": "90,00",
            "preis": "1,800", "tank_voll": "on"})
        self.assertEqual(antwort.status_code, 302, getattr(antwort, "context", {}) and antwort.context["form"].errors)
        e = Eintrag.objects.get(tachostand=3100)
        self.assertEqual(e.menge, Decimal("50.000"))
        self.assertEqual(e.erfasst_von, self.a)

    def test_unplausibler_tachostand(self):
        daten = {"kraftstoff_nr": "1", "tachostand": "900", "zeitpunkt": "2026-03-20T08:00", "kosten": "50",
                 "menge": "30", "tank_voll": "on"}
        antwort = self.client.post(reverse("logbuch:neu", args=[self.f.pk, "tanken"]), daten)
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort.context["form"].non_field_errors())
        antwort = self.client.post(reverse("logbuch:neu", args=[self.f.pk, "tanken"]), {**daten, "trotzdem": "on"})
        self.assertEqual(antwort.status_code, 302)

    def _fahrt(self, ziel, **extra):
        return self.client.post(reverse("logbuch:neu", args=[self.f.pk, "fahrt"]), {
            "start_zeitpunkt": "2026-03-21T08:00", "start_km": "2500", "start_ort_name": "Zuhause",
            "zeitpunkt": "2026-03-21T12:00", "tachostand": ziel, "ort_name": "Ostsee", **extra})

    def test_fahrt(self):
        antwort = self._fahrt("2.800")
        self.assertEqual(antwort.status_code, 302)
        e = Eintrag.objects.get(ort__name="Ostsee")
        self.assertEqual((e.fahrtstrecke, e.kosten, e.start_ort.name), (300, 0, "Zuhause"))

    def test_fahrt_formel(self):
        self.assertEqual(self._fahrt("=345+28+70").status_code, 302)
        self.assertEqual(Eintrag.objects.get(ort__name="Ostsee").tachostand, 2943)

    def test_fahrt_formel_eine_zahl_und_fehler(self):
        self.assertEqual(self._fahrt("= 443").status_code, 302)
        self.assertEqual(Eintrag.objects.get(ort__name="Ostsee").tachostand, 2943)
        antwort = self._fahrt("=12+abc")
        self.assertIn("tachostand", antwort.context["form"].errors)
        antwort = self._fahrt("=443", start_km="")
        self.assertTrue(antwort.context["form"].errors)

    def test_orte_auswahl_umbenennen_zusammenfuehren(self):
        from logbuch.models import Ort
        self._fahrt("2800")
        antwort = self.client.get(reverse("logbuch:neu", args=[self.f.pk, "fahrt"]))
        self.assertContains(antwort, '<option value="Ostsee">')
        self.assertEqual(antwort.context["form"].initial["start_ort_name"], "Ostsee")   # Ziel der letzten Fahrt
        self._fahrt("=10", start_km="2800", ort_name=" ostsee  ")                       # kein zweiter Ort
        self.assertEqual(Ort.objects.filter(familie=self.familie, name__iexact="ostsee").count(), 1)
        zuhause = Ort.objects.get(name="Zuhause")
        ostsee = Ort.objects.get(name="Ostsee")
        self.client.post(reverse("logbuch:ort", args=[zuhause.pk]), {"name": "Daheim"})
        self.assertEqual(Eintrag.objects.filter(start_ort__name="Daheim").count(), 2)
        self.client.post(reverse("logbuch:ort", args=[ostsee.pk]), {"name": "daheim"})
        self.assertFalse(Ort.objects.filter(pk=ostsee.pk).exists())
        self.assertEqual(Eintrag.objects.filter(ort__name="Daheim").count(), 2)
        self.assertEqual(self.client.get(reverse("logbuch:orte")).status_code, 200)

    def test_erinnerung_erledigen_legt_naechste_an(self):
        kat = Kategorie.objects.get(familie=self.familie, name="TÜV")
        er = Erinnerung.objects.create(fahrzeug=self.f, kategorie=kat, faellig_am=date(2026, 4, 1), wiederholen_monate=24)
        antwort = self.client.post(reverse("logbuch:erledigt", args=[self.f.pk, er.pk]),
                                   {"datum": "2026-03-25", "tachostand": "2600", "kosten": "140", "ort": "Dekra"})
        self.assertEqual(antwort.status_code, 302)
        er.refresh_from_db()
        self.assertEqual(er.erledigt_am, date(2026, 3, 25))
        self.assertTrue(Erinnerung.objects.filter(faellig_am=date(2028, 4, 1), erledigt_am__isnull=True).exists())
        self.assertTrue(Eintrag.objects.filter(kategorie=kat, kosten=140).exists())

    def test_serie_bucht(self):
        kat = Kategorie.objects.get(familie=self.familie, name="Versicherung")
        heute = date.today()
        antwort = self.client.post(reverse("logbuch:serie_neu", args=[self.f.pk]), {
            "kategorie": kat.pk, "betrag": "45,50", "intervall_monate": "1",
            "beginn": (heute - timedelta(days=70)).isoformat()})
        self.assertEqual(antwort.status_code, 302)
        serie = Serie.objects.get()
        self.assertGreaterEqual(serie.eintraege.count(), 2)
        anzahl = serie.eintraege.count()
        call_command("serien_buchen", stdout=open("/dev/null", "w"))
        self.assertEqual(serie.eintraege.count(), anzahl)

    def test_erinnerungsmail_einmal(self):
        kat = Kategorie.objects.get(familie=self.familie, name="TÜV")
        Erinnerung.objects.create(fahrzeug=self.f, kategorie=kat, faellig_am=date.today() + timedelta(days=5))
        Erinnerung.objects.create(fahrzeug=self.f, kategorie=kat, faellig_am=date.today() + timedelta(days=200))
        call_command("erinnerungen", stdout=open("/dev/null", "w"))
        self.assertEqual(len(mail.outbox), 2)   # beide Personen der Familie
        self.assertIn("TÜV", mail.outbox[0].subject)
        call_command("erinnerungen", stdout=open("/dev/null", "w"))
        self.assertEqual(len(mail.outbox), 2)

    def test_einladung(self):
        antwort = self.client.post(reverse("portal:familie"), {"name": "Carl", "email": "C@Example.org"})
        self.assertEqual(antwort.status_code, 302)
        carl = Person.objects.get(email="c@example.org")
        self.assertEqual(carl.familie, self.familie)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/anmelden/link/", mail.outbox[0].body)


class AnmeldungTest(TestCase):
    def setUp(self):
        self.familie, self.a = familie_mit_person("Muster", "a@example.org")

    def test_magic_link(self):
        antwort = self.client.post("/anmelden/", {"email": "A@example.org "})
        self.assertRedirects(antwort, "/anmelden/gesendet/")
        link = [z for z in mail.outbox[0].body.split() if "/anmelden/link/" in z][0]
        pfad = link.split("://", 1)[-1].split("/", 1)[1]
        self.assertEqual(self.client.get("/" + pfad).status_code, 200)   # GET meldet nicht an
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.post("/" + pfad)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.a.pk)
        self.client.logout()
        self.client.post("/" + pfad)   # nur einmal gültig
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unbekannte_adresse_gleiche_antwort(self):
        antwort = self.client.post("/anmelden/", {"email": "niemand@example.org"})
        self.assertRedirects(antwort, "/anmelden/gesendet/")
        self.assertEqual(len(mail.outbox), 0)

    def test_begrenzung(self):
        for _ in range(7):
            self.client.post("/anmelden/", {"email": "a@example.org"})
        self.assertEqual(MagicLinkToken.objects.filter(person=self.a).count(), 5)

    def test_ohne_anmeldung_umgeleitet(self):
        self.assertRedirects(self.client.get("/"), "/anmelden/?next=/")


class OfflineTest(TestCase):
    def test_offline_seite_ohne_anmeldung(self):
        antwort = self.client.get("/offline/")
        self.assertContains(antwort, "Keine Verbindung")
        self.assertNotContains(antwort, "Abmelden")

    def test_service_worker(self):
        antwort = self.client.get("/sw.js")
        self.assertEqual(antwort["Content-Type"], "text/javascript")
        self.assertEqual(antwort["Cache-Control"], "no-cache")
        self.assertContains(antwort, 'const OFFLINE = "/offline/"')
        self.assertContains(antwort, "drive.css")

    def test_registrierung_in_jeder_seite(self):
        self.assertContains(self.client.get("/anmelden/"), 'serviceWorker.register("/sw.js")')

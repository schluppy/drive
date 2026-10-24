from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from fahrzeuge.models import Fahrzeug
from importe import drivenote, uebernahme
from logbuch.models import Eintrag, Erinnerung, Kategorie

from .hilfen import backup_zip, fahrzeug, familie_mit_person


@override_settings(MEDIA_ROOT="/tmp/drive-test-media")
class ImportTest(TestCase):
    def setUp(self):
        self.familie, self.person = familie_mit_person("Muster", "a@example.org")

    def _import(self, person=None, zuordnung=None, **kwargs):
        person = person or self.person
        backup = drivenote.lesen(backup_zip(**kwargs))
        wahl = zuordnung or uebernahme.vorschlag(backup, person.familie)
        return uebernahme.uebernehmen(backup, person, wahl)

    def test_fahrzeuge_und_felder(self):
        bericht = self._import()
        self.assertEqual(len(bericht.fahrzeuge_neu), 2)   # gelöschtes Fahrzeug fehlt
        tucson = Fahrzeug.objects.get(import_uuid="uuid-fz-1")
        self.assertEqual((tucson.kraftstoff, tucson.kraftstoff2), ("diesel", "adblue"))
        self.assertEqual(tucson.tankvolumen, Decimal("62.0"))
        self.assertEqual(tucson.erwerb_datum, date(2023, 11, 18))
        self.assertEqual(tucson.erwerb_km, 56587)
        self.assertEqual(tucson.halter, self.person)
        self.assertTrue(tucson.foto)
        wohnwagen = Fahrzeug.objects.get(import_uuid="uuid-fz-3")
        self.assertEqual(wohnwagen.art, "wohnwagen")
        self.assertEqual(wohnwagen.kraftstoff, "")

    def test_eintraege(self):
        self._import()
        self.assertFalse(Eintrag.objects.filter(import_uuid="uuid-geloescht").exists())
        voll = Eintrag.objects.get(import_uuid="uuid-lb-1")
        self.assertEqual((voll.tachostand, voll.menge, voll.kosten), (61200, Decimal("47.000"), Decimal("82.00")))
        self.assertEqual(voll.bc_verbrauch, Decimal("7.50"))
        self.assertTrue(voll.tank_voll)
        teil = Eintrag.objects.get(import_uuid="uuid-adblue-2")
        self.assertEqual(teil.kraftstoff_nr, 2)
        self.assertFalse(teil.tank_voll)
        fahrt = Eintrag.objects.get(import_uuid="uuid-fahrt")
        self.assertEqual(fahrt.kategorie.art, "fahrt")
        self.assertEqual((fahrt.start_km, fahrt.tachostand, fahrt.start_ort.name, fahrt.ort.name, fahrt.kosten),
                         (25826, 25942, "Camping SPO", "Kölln-Reisiek", 0))
        camp = Eintrag.objects.get(import_uuid="uuid-camp")
        self.assertEqual(camp.ort, fahrt.start_ort)   # derselbe Ort
        self.assertEqual(fahrt.fahrtstrecke, 116)
        waesche = Eintrag.objects.get(import_uuid="uuid-waesche")
        self.assertEqual(waesche.kategorie.name, "Autowäsche")   # vorhandene Kategorie wiederverwendet
        self.assertEqual(waesche.beschreibung, "")
        self.assertTrue(Kategorie.objects.filter(familie=self.familie, name="Campingplatz").exists())

    def test_erinnerungen(self):
        self._import()
        tuev = Erinnerung.objects.get(import_uuid="uuid-er-tuev")
        self.assertEqual(tuev.faellig_am, date(2027, 12, 1))
        self.assertEqual(tuev.wiederholen_monate, 24)
        km = Erinnerung.objects.get(import_uuid="uuid-er-km")
        self.assertEqual((km.faellig_km, km.wiederholen_monate, km.notiz), (97000, None, "Bremsen hinten"))

    def test_wiederholen_aktualisiert_statt_verdoppelt(self):
        self._import()
        anzahl = Eintrag.objects.count()
        bericht = self._import()
        self.assertEqual(Eintrag.objects.count(), anzahl)
        self.assertEqual(bericht.eintraege_neu, 0)
        self.assertEqual(Fahrzeug.objects.count(), 2)

    def test_zweite_person_fuehrt_dasselbe_auto(self):
        """Gleiches Kennzeichen → Vorschlag: vorhandenes Fahrzeug; gleiche Einträge werden nicht doppelt."""
        self._import()
        from konten.models import Person
        zweite = Person.objects.create_user("b@example.org", "Zweite", familie=self.familie)
        backup = drivenote.lesen(backup_zip(fahrzeuge=[
            {"_vid": "7", "v8": "0", "v9": "anderes-handy", "v20": "Hyundai", "v21": "Tucson", "v23": "AB C123",
             "v25": "11", "v53": "30", "v50": "1"}],
            logbuch=[{"_lid": "1", "vid": "7", "cid": "8", "l8": "0", "l9": "x1", "l10": "1767481200000",
                      "l11": "62400.0", "l12": "84.0", "l20": "49.0", "l26": "0", "l27": "100.0"},
                     {"_lid": "2", "vid": "7", "cid": "8", "l8": "0", "l9": "x2", "l10": "1767740400000",
                      "l11": "63500.0", "l12": "90.0", "l20": "50.0", "l26": "0", "l27": "100.0"}],
            erinnerungen=[]))
        wahl = uebernahme.vorschlag(backup, self.familie)
        tucson = Fahrzeug.objects.get(import_uuid="uuid-fz-1")
        self.assertEqual(wahl["7"], str(tucson.pk))
        bericht = uebernahme.uebernehmen(backup, zweite, wahl)
        self.assertEqual(bericht.eintraege_doppelt, 1)    # 04.01.2026 / 62400 km gibt es schon
        self.assertEqual(bericht.eintraege_neu, 1)
        self.assertEqual(Eintrag.objects.get(import_uuid="x2").erfasst_von, zweite)
        self.assertEqual(Fahrzeug.objects.count(), 2)

    def test_auslassen(self):
        backup = drivenote.lesen(backup_zip())
        uebernahme.uebernehmen(backup, self.person, {"1": "neu", "3": "aus"})
        self.assertEqual(Fahrzeug.objects.count(), 1)

    def test_fremdes_fahrzeug_nicht_zuordenbar(self):
        andere, _ = familie_mit_person("Andere", "x@example.org")
        fremd = fahrzeug(andere)
        backup = drivenote.lesen(backup_zip())
        with self.assertRaises(Fahrzeug.DoesNotExist):
            uebernahme.uebernehmen(backup, self.person, {"1": str(fremd.pk)})

    def test_kaputtes_backup(self):
        import io
        with self.assertRaises(drivenote.BackupFehler):
            drivenote.lesen(io.BytesIO(b"kein zip"))

    def test_hochladen_ohne_dateiendung(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from django.core.files.uploadedfile import SimpleUploadedFile
        ordner = Path(tempfile.mkdtemp()) / "import"
        self.enterContext(mock.patch("importe.views.ORDNER", ordner))
        self.client.force_login(self.person)
        seite = self.client.get("/import/")
        self.assertNotContains(seite, "accept=")
        datei = SimpleUploadedFile("Drivenote Backup 13.10.26", backup_zip().read(),
                                   content_type="application/octet-stream")
        antwort = self.client.post("/import/", {"backup": datei})
        self.assertRedirects(antwort, "/import/zuordnen/")

from datetime import date
from decimal import Decimal

from django.test import TestCase

from auswertung.kennzahlen import kennzahlen
from logbuch import verbrauch as vb
from logbuch.models import Erinnerung, Kategorie
from portal.templatetags.drive import zeitraum

from .hilfen import fahrzeug, familie_mit_person, tanken


class VerbrauchTest(TestCase):
    def setUp(self):
        self.familie, self.person = familie_mit_person("Muster", "a@example.org")
        self.f = fahrzeug(self.familie, self.person, kraftstoff2="adblue")

    def test_voll_bis_voll(self):
        tanken(self.f, "01.01.2026", 1000, 50, 80)          # Anker, zählt nicht
        tanken(self.f, "05.01.2026", 1600, 42, 70, bc=6.5)
        tanken(self.f, "10.01.2026", 2400, 60, 100, bc=7.0)
        v = kennzahlen(self.f).kraftstoff(1).verbrauch
        self.assertAlmostEqual(v.gesamt, Decimal(102) / 1400 * 100)
        self.assertAlmostEqual(v.aktuell, Decimal(60) / 800 * 100)
        self.assertEqual(v.trend, "hoch")
        # Bordcomputer nach Strecke gewichtet
        self.assertAlmostEqual(v.bc, (Decimal("6.5") * 600 + Decimal(7) * 800) / 1400)
        self.assertEqual(v.km, 1400)

    def test_teilfuellung_zaehlt_zum_naechsten_vollen_tank(self):
        tanken(self.f, "01.01.2026", 1000, 50, 80)
        tanken(self.f, "03.01.2026", 1300, 10, 16, voll=False)
        tanken(self.f, "05.01.2026", 1600, 30, 50)
        a = vb.abschnitte(vb.tankfuellungen(self.f))
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0].menge, 40)
        self.assertEqual(a[0].km, 600)
        self.assertEqual(a[0].kosten, 66)

    def test_vorherige_fehlt_beginnt_neue_kette(self):
        tanken(self.f, "01.01.2026", 1000, 50, 80)
        tanken(self.f, "05.01.2026", 1600, 40, 70)
        tanken(self.f, "20.01.2026", 3000, 45, 70, fehlt=True)   # Strecke 1600 → 3000 zählt nicht
        tanken(self.f, "25.01.2026", 3500, 35, 60)
        a = vb.abschnitte(vb.tankfuellungen(self.f))
        self.assertEqual([x.km for x in a], [600, 500])

    def test_kraftstoffe_getrennt(self):
        tanken(self.f, "01.01.2026", 1000, 50, 80)
        tanken(self.f, "01.01.2026", 1000, 5, 8, nr=2)
        tanken(self.f, "05.01.2026", 2000, 60, 100)
        tanken(self.f, "05.01.2026", 2000, 2, 3, nr=2)
        kz = kennzahlen(self.f)
        self.assertAlmostEqual(kz.kraftstoff(1).verbrauch.gesamt, Decimal(6))
        self.assertAlmostEqual(kz.kraftstoff(2).verbrauch.gesamt, Decimal("0.2"))
        # Kosten je km: alle Tankkosten / Strecke erste bis letzte Tankfüllung
        self.assertAlmostEqual(kz.kraftstoff(1).kosten_je_km, Decimal("0.18"))

    def test_fahrleistung_ab_kauf(self):
        self.f.erwerb_km = 500
        self.f.save()
        tanken(self.f, "01.01.2026", 1000, 50, 80)
        tanken(self.f, "05.01.2026", 2000, 60, 100)
        kz = kennzahlen(self.f)
        self.assertEqual(kz.fahrleistung, 1500)
        self.assertAlmostEqual(kz.kosten_je_km, Decimal(180) / 1500)

    def test_jahresfahrleistung(self):
        tanken(self.f, "01.06.2025", 1000, 50, 80)
        tanken(self.f, "20.12.2025", 9000, 50, 80)
        tanken(self.f, "05.03.2026", 12000, 60, 100)
        self.assertEqual(vb.jahresfahrleistung(self.f), {2025: 8000, 2026: 3000})

    def test_faelligkeit_schaetzt_datum_aus_km(self):
        kat = Kategorie.objects.get(familie=self.familie, name="Reparatur")
        e = Erinnerung(fahrzeug=self.f, kategorie=kat, faellig_km=11000)
        fl = vb.faelligkeit(e, 10000, Decimal(50), heute=date(2026, 1, 1))
        self.assertEqual(fl.km_rest, 1000)
        self.assertEqual(fl.datum_geschaetzt, date(2026, 1, 21))

    def test_naechste_erinnerung(self):
        kat = Kategorie.objects.get(familie=self.familie, name="Inspektion")
        e = Erinnerung(fahrzeug=self.f, kategorie=kat, faellig_am=date(2026, 2, 1), faellig_km=90000,
                       wiederholen_monate=24, wiederholen_km=30000)
        n = e.naechste(date(2026, 1, 20), 89000)
        self.assertEqual(n.faellig_am, date(2028, 2, 1))
        self.assertEqual(n.faellig_km, 120000)

    def test_zeitraum_wie_drivenote(self):
        heute = date(2026, 10, 23)
        self.assertEqual(zeitraum(404, heute), "+1 Jahr, 1 Monat, 8 Tage")
        self.assertEqual(zeitraum(466, heute), "+1 Jahr, 3 Monate, 9 Tage")
        self.assertEqual(zeitraum(20, heute), "+20 Tage")

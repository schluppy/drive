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
        jf = vb.jahresfahrleistung(self.f)
        # der 1.1.2026 liegt 12 von 75 Tagen nach dem 20.12.2025: Stand 9000 + 3000 × 12/75 = 9480
        self.assertAlmostEqual(jf[2025].km, Decimal(8480))
        self.assertAlmostEqual(jf[2026].km, Decimal(2520))

    def test_wohnwagen_fahrten_und_prognose(self):
        from logbuch.models import Eintrag, Kategorieart
        from .hilfen import zp
        wohnwagen = fahrzeug(self.familie, self.person, art="wohnwagen", kraftstoff="")
        fahrt = Kategorie.fuer(self.familie, Kategorieart.FAHRT)
        Eintrag.objects.create(fahrzeug=wohnwagen, kategorie=fahrt, start_km=0, zeitpunkt=zp("01.01.2026"), tachostand=100)
        Eintrag.objects.create(fahrzeug=wohnwagen, kategorie=fahrt, start_km=100, zeitpunkt=zp("02.03.2026"),
                               tachostand=700)
        fl = vb.fahrleistung_kennzahlen(wohnwagen, heute=date(2026, 12, 1))
        self.assertEqual(fl.gesamt, 600)
        self.assertAlmostEqual(fl.pro_tag, Decimal(10))
        self.assertAlmostEqual(fl.prognose, 600 + 10 * 31)
        z = vb.jahresfahrleistung(wohnwagen)[2026]
        self.assertEqual((z.erster, z.letzter, z.km), (100, 700, 600))

    def test_jahresgrenze_interpoliert(self):
        tanken(self.f, "01.12.2025", 1000, 50, 80)
        tanken(self.f, "31.01.2026", 1620, 50, 80)
        jf = vb.jahresfahrleistung(self.f)
        self.assertAlmostEqual(jf[2025].letzter, 1000 + Decimal(620) * 31 / 61)   # 31 von 61 Tagen
        self.assertAlmostEqual(jf[2025].km + jf[2026].km, Decimal(620))

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

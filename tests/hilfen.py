"""Testdaten: Familien, Fahrzeuge, Einträge und ein künstliches DriveNote-Backup."""
import gzip
import io
import zipfile
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from fahrzeuge.models import Fahrzeug
from konten.models import Familie, Person
from logbuch.models import Eintrag, Kategorie, Kategorieart


def familie_mit_person(name, email):
    familie = Familie.objects.create(name=name)
    person = Person.objects.create_user(email, f"{name} Person", familie=familie)
    return familie, person


def fahrzeug(familie, halter=None, **felder):
    werte = {"hersteller": "Testwagen", "modell": "T1", "kraftstoff": "diesel", "tankvolumen": Decimal(60)}
    werte.update(felder)
    return Fahrzeug.objects.create(familie=familie, halter=halter, **werte)


def zp(text):
    return timezone.make_aware(datetime.strptime(text, "%d.%m.%Y"))


def tanken(f, datum, km, liter, kosten, voll=True, nr=1, fehlt=False, bc=None, person=None):
    return Eintrag.objects.create(
        fahrzeug=f, kategorie=Kategorie.fuer(f.familie, Kategorieart.TANKEN), zeitpunkt=zp(datum), tachostand=km,
        menge=Decimal(str(liter)), kosten=Decimal(str(kosten)), tank_voll=voll, kraftstoff_nr=nr,
        vorherige_fehlt=fehlt, bc_verbrauch=Decimal(str(bc)) if bc else None, erfasst_von=person)


# --- künstliches DriveNote-Backup -------------------------------------------------

def _xml(zeilen):
    teile = ['<?xml version="1.0" encoding="utf-8"?><l ver="2">']
    for z in zeilen:
        teile.append("<e>" + "".join(f'<i n="{k}">{v}</i>' for k, v in z.items()) + "</e>")
    teile.append("</l>")
    return gzip.compress("".join(teile).encode())


def _ms(text):
    return str(int(zp(text).timestamp() * 1000))


def backup_zip(fahrzeuge=None, kategorien=None, logbuch=None, erinnerungen=None, fotos=None):
    """Baut ein Backup im Format von DriveNote 1.11 (fVer 15)."""
    fahrzeuge = fahrzeuge if fahrzeuge is not None else [
        {"_vid": "1", "v8": "0", "v9": "uuid-fz-1", "v20": "Hyundai", "v21": "Tucson", "v22": "Grau",
         "v23": "AB-C 123", "v24": "185 PS", "v25": "11", "v26": "62.0", "v50": "1", "v54": "14.0", "v53": "30",
         "v28": _ms("13.09.2019"), "v37": _ms("16.04.2020"), "v29": _ms("18.11.2023"), "v30": "56587.0",
         "v31": "25270.0", "v32": "null", "v33": "null", "v34": "null", "v35": "null", "v36": "LVM", "v40": "foto-1"},
        {"_vid": "2", "v8": "1", "v9": "uuid-fz-geloescht", "v20": "Weg", "v21": "damit", "v53": "30", "v25": "10"},
        {"_vid": "3", "v8": "0", "v9": "uuid-fz-3", "v20": "LMC", "v21": "530 E", "v23": "AB-C 2022", "v53": "10",
         "v25": "10", "v50": "0", "v40": "null"},
    ]
    kategorien = kategorien if kategorien is not None else [
        {"_cid": "8", "c1": "1", "c8": "0", "c9": "uuid-kat-tanken", "c10": "Tankfüllung", "c11": "-10177034"},
        {"_cid": "9", "c1": "2", "c8": "0", "c9": "uuid-kat-fahrt", "c10": "Wohnwagen-Fahrt", "c11": "-11677471"},
        {"_cid": "969", "c1": "0", "c8": "0", "c9": "uuid-kat-waesche", "c10": "Autowäsche", "c11": "-8604862"},
        {"_cid": "5", "c1": "0", "c8": "0", "c9": "uuid-kat-tuev", "c10": "TÜV", "c11": "-6982195"},
        {"_cid": "3383", "c1": "0", "c8": "0", "c9": "uuid-kat-camp", "c10": "Campingplatz ", "c11": "-3722"},
    ]
    if logbuch is None:
        logbuch = []
        stand = [(f"0{t}.01.2026", 60000 + 600 * t, 45.0 + t, 80.0 + t, None) for t in range(1, 6)]
        for i, (d, km, l, k, bc) in enumerate(stand):
            logbuch.append({"_lid": str(i + 1), "vid": "1", "cid": "8", "l8": "0", "l9": f"uuid-lb-{i}",
                            "l10": _ms(d), "l11": f"{km}.0", "l12": str(k), "l20": str(l), "l22": "0",
                            "l26": "0", "l27": "100.0", "l25": "7.5"})
        logbuch += [
            {"_lid": "20", "vid": "1", "cid": "8", "l8": "0", "l9": "uuid-adblue-1", "l10": _ms("01.01.2026"),
             "l11": "60600.0", "l12": "9.0", "l20": "8.0", "l26": "1", "l27": "100.0"},
            {"_lid": "21", "vid": "1", "cid": "8", "l8": "0", "l9": "uuid-adblue-2", "l10": _ms("05.01.2026"),
             "l11": "63000.0", "l12": "5.0", "l20": "4.5", "l26": "1", "l27": "0.0"},
            {"_lid": "30", "vid": "1", "cid": "969", "l8": "0", "l9": "uuid-waesche", "l10": _ms("06.01.2026"),
             "l11": "63100.0", "l12": "12.0", "l23": "Waschanlage", "l13": "null"},
            {"_lid": "31", "vid": "1", "cid": "969", "l8": "1", "l9": "uuid-geloescht", "l10": _ms("07.01.2026"),
             "l11": "63200.0", "l12": "99.0"},
            {"_lid": "40", "vid": "3", "cid": "9", "l8": "0", "l9": "uuid-fahrt", "l10": _ms("10.01.2026"),
             "l11": "25942.0", "l12": "0.0", "l23": "Kölln-Reisiek", "l31": "Camping SPO", "l30": "25826.0",
             "l33": _ms("09.01.2026"), "l13": "LMC Treffen"},
            {"_lid": "41", "vid": "3", "cid": "3383", "l8": "0", "l9": "uuid-camp", "l10": _ms("09.01.2026"),
             "l11": "25826.0", "l12": "238.0", "l23": "Camping SPO"},
        ]
    erinnerungen = erinnerungen if erinnerungen is not None else [
        {"_rid": "1", "vid": "1", "cid": "5", "r8": "0", "r9": "uuid-er-tuev", "r10": _ms("01.12.2027"),
         "r11": "null", "r20": "0", "r40": "1", "r43": "2", "r50": "0", "r52": "1.0", "r30": "null"},
        {"_rid": "2", "vid": "1", "cid": "969", "r8": "0", "r9": "uuid-er-km", "r10": "null", "r11": "97000.0",
         "r20": "0", "r40": "0", "r43": "1", "r50": "0", "r52": "1.0", "r30": "Bremsen hinten"},
    ]
    from PIL import Image
    puffer = io.BytesIO()
    Image.new("RGB", (40, 30), "#336699").save(puffer, "JPEG")
    fotos = fotos if fotos is not None else {"foto-1": puffer.getvalue()}

    db = io.BytesIO()
    with zipfile.ZipFile(db, "w") as z:
        z.writestr("vh.s", _xml(fahrzeuge))
        z.writestr("cg.s", _xml(kategorien))
        z.writestr("lb.s", _xml(logbuch))
        z.writestr("rm.s", _xml(erinnerungen))
        z.writestr("rl.s", _xml([]))
    pv = io.BytesIO()
    with zipfile.ZipFile(pv, "w") as z:
        for name, daten in fotos.items():
            z.writestr(name, gzip.compress(daten))
    aussen = io.BytesIO()
    with zipfile.ZipFile(aussen, "w") as z:
        z.writestr("META", '<?xml version="1.0" encoding="utf-8"?><meta><param name="fVer">15</param>'
                           '<param name="aV">1.11.12</param><param name="hMl">Testhandy</param></meta>')
        z.writestr("db.d", db.getvalue())
        z.writestr("pv.d", pv.getvalue())
        z.writestr("st.p", gzip.compress(b"<p/>"))
    aussen.seek(0)
    return aussen

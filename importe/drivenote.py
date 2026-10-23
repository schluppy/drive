"""Import eines DriveNote-Backups (Android-App de.drivenote.android, Backup-Format 15).

Aufbau des Backups (ZIP):

    META   XML mit App-Version und Prüfsummen
    st.p   gzip: Einstellungen der App (nicht übernommen)
    db.d   ZIP mit gzip-komprimierten XML-Tabellen:
           vh.s Fahrzeuge, cg.s Kategorien, lb.s Logbuch, rm.s Erinnerungen,
           rl.s Serien, st.s Statistik-Einstellungen
    pv.d   ZIP mit den Fahrzeugfotos (JPEG), Name = UUID aus vh.s

Jede Tabelle ist `<l><e><i n="feld">wert</i>…</e>…</l>`. Die Feldnamen sind kurz
und undokumentiert; die Bedeutung unten ist an echten Daten und Screenshots der
App geprüft. `x8 = 1` heißt in allen Tabellen „gelöscht“, `x9` ist die UUID.
Zeitpunkte in Millisekunden seit 1970, „null“ steht für leer.

Der Import ist wiederholbar: Einträge mit bekannter UUID werden aktualisiert,
nicht doppelt angelegt.
"""
import gzip
import io
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone as tz
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from defusedxml import ElementTree

MAX_ENTPACKT = 200 * 1024 * 1024   # Schutz vor ZIP-Bomben
TABELLEN = {"vh.s", "cg.s", "lb.s", "rm.s", "rl.s", "st.s"}


class BackupFehler(Exception):
    pass


# --- Rohdaten lesen ------------------------------------------------------------

def _zip(daten, was):
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
    except zipfile.BadZipFile as e:
        raise BackupFehler(f"{was} ist keine ZIP-Datei") from e
    if sum(i.file_size for i in z.infolist()) > MAX_ENTPACKT:
        raise BackupFehler(f"{was} ist entpackt zu groß")
    return z


def _entpacken(daten):
    return gzip.decompress(daten) if daten[:2] == b"\x1f\x8b" else daten


def _tabelle(xml):
    try:
        wurzel = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise BackupFehler("Tabelle im Backup nicht lesbar") from e
    zeilen = []
    for e in wurzel:
        zeile = {}
        for i in e:
            wert = i.text
            zeile[i.get("n")] = None if wert in (None, "null", "") else wert.strip()
        zeilen.append(zeile)
    return zeilen


@dataclass
class Backup:
    meta: dict
    tabellen: dict
    fotos: dict = field(default_factory=dict)

    def zeilen(self, name):
        """Tabellenzeilen ohne gelöschte"""
        return [z for z in self.tabellen.get(name, []) if not _wahr(_feld(z, "8"))]


def _feld(zeile, nr):
    """Feld unabhängig vom Präfix: _feld(z, '8') findet v8, c8, l8 oder r8."""
    for k, v in zeile.items():
        if k[1:] == nr and k[0] in "vclrs":
            return v
    return None


def lesen(datei):
    """Liest ein Backup aus einer Datei (Pfad oder Dateiobjekt)."""
    if hasattr(datei, "read"):
        daten = datei.read()
    else:
        with open(datei, "rb") as f:
            daten = f.read()
    aussen = _zip(daten, "Das Backup")
    namen = set(aussen.namelist())
    if "db.d" not in namen:
        raise BackupFehler("Das ist kein DriveNote-Backup (db.d fehlt).")
    meta = {}
    if "META" in namen:
        try:
            wurzel = ElementTree.fromstring(aussen.read("META"))
            meta = {p.get("name"): p.text for p in wurzel}
        except ElementTree.ParseError:
            pass
    db = _zip(aussen.read("db.d"), "db.d")
    tabellen = {}
    for name in db.namelist():
        if name in TABELLEN:
            tabellen[name] = _tabelle(_entpacken(db.read(name)))
    if "vh.s" not in tabellen or "lb.s" not in tabellen:
        raise BackupFehler("Im Backup fehlen Fahrzeuge oder Logbuch.")
    fotos = {}
    if "pv.d" in namen:
        pv = _zip(aussen.read("pv.d"), "pv.d")
        for name in pv.namelist():
            fotos[name] = _entpacken(pv.read(name))
    return Backup(meta, tabellen, fotos)


# --- Werte umwandeln ---------------------------------------------------------

def _wahr(wert):
    return wert == "1"


def _zahl(wert, stellen=None):
    if wert is None:
        return None
    try:
        d = Decimal(wert)
    except InvalidOperation:
        return None
    if stellen is not None:
        d = d.quantize(Decimal(1).scaleb(-stellen), ROUND_HALF_UP)
    return d


def _ganz(wert):
    d = _zahl(wert, 0)
    return int(d) if d is not None else None


def zeitpunkt(ms):
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=tz.utc)
    except (ValueError, OverflowError):
        return None


def tag(ms):
    """Kalendertag eines in der App gewählten Datums (lokale Mitternacht als UTC-Millisekunden)."""
    from django.utils import timezone
    z = zeitpunkt(ms)
    return timezone.localtime(z).date() if z else None


def farbe(argb):
    """Android-Farbe (vorzeichenbehaftetes ARGB) → #rrggbb"""
    try:
        return f"#{int(argb) & 0xFFFFFF:06x}"
    except (TypeError, ValueError):
        return "#bdbdbd"


# Kraftstoffcodes in vh.s v25. Gesichert ist nur 11 = Diesel (eigenes Fahrzeug);
# die übrigen sind die Reihenfolge der Auswahl in der App und werden beim Import angezeigt.
KRAFTSTOFFE = {"10": "super", "11": "diesel", "12": "lpg", "13": "cng", "14": "strom", "15": "e10",
               "16": "superplus"}

KATEGORIE_ART = {"0": "kosten", "1": "tanken", "2": "fahrt"}

SYMBOL_NACH_NAME = [
    ("tank", "tanken"), ("fahrt", "fahrt"), ("inspektion", "inspektion"), ("reparatur", "reparatur"),
    ("versicherung", "versicherung"), ("steuer", "steuer"), ("tüv", "tuev"), ("hu", "tuev"),
    ("reifen", "reifen"), ("wäsche", "waesche"), ("wasch", "waesche"), ("öl", "oel"), ("additiv", "additiv"),
    ("camping", "camping"), ("gas", "gas"), ("park", "parken"), ("maut", "maut"), ("vignette", "maut"),
]


def symbol_fuer(name):
    name = name.lower()
    for teil, symbol in SYMBOL_NACH_NAME:
        if teil in name:
            return symbol
    return "sonstiges"


@dataclass
class FahrzeugDaten:
    nr: str
    uuid: str
    felder: dict
    foto: bytes | None
    eintraege: int = 0
    kraftstoff_unsicher: bool = False

    @property
    def name(self):
        return f"{self.felder['hersteller']} {self.felder['modell']}".strip()


def fahrzeuge(backup):
    zaehler = {}
    for z in backup.zeilen("lb.s"):
        zaehler[z.get("vid")] = zaehler.get(z.get("vid"), 0) + 1
    liste = []
    for z in backup.zeilen("vh.s"):
        pkw = z.get("v53") != "10"
        code = z.get("v25")
        felder = {
            "art": "pkw" if pkw else "wohnwagen",   # Anhänger ohne Motor kennt DriveNote nicht getrennt
            "hersteller": (z.get("v20") or "Fahrzeug").strip(),
            "modell": (z.get("v21") or "").strip(),
            "beschreibung": (z.get("v22") or "").strip(),
            "kennzeichen": (z.get("v23") or "").strip(),
            "motorisierung": (z.get("v24") or "").strip(),
            "fin": (z.get("v35") or "").strip(),
            "versicherung": (z.get("v36") or "").strip(),
            "kraftstoff": KRAFTSTOFFE.get(code, "super") if pkw else "",
            "tankvolumen": _zahl(z.get("v26"), 1) if pkw else None,
            "kraftstoff2": "adblue" if pkw and _wahr(z.get("v50")) else "",
            "tankvolumen2": _zahl(z.get("v54"), 1) if pkw and _wahr(z.get("v50")) else None,
            "hergestellt_am": tag(z.get("v28")),
            "erstzulassung": tag(z.get("v37")),
            "erwerb_datum": tag(z.get("v29")),
            "erwerb_km": _ganz(z.get("v30")),
            "erwerb_preis": _zahl(z.get("v31"), 2),
            "verkauf_datum": tag(z.get("v32")),
            "verkauf_km": _ganz(z.get("v33")),
            "verkauf_preis": _zahl(z.get("v34"), 2),
        }
        liste.append(FahrzeugDaten(
            nr=z.get("_vid"), uuid=z.get("v9") or "", felder=felder,
            foto=backup.fotos.get(z.get("v40") or ""), eintraege=zaehler.get(z.get("_vid"), 0),
            kraftstoff_unsicher=pkw and code != "11"))
    return liste


def kategorien(backup):
    """{cid: {name, art, farbe, symbol, uuid}} – auch gelöschte, falls Einträge noch darauf zeigen."""
    ergebnis = {}
    for z in backup.tabellen.get("cg.s", []):
        name = (z.get("c10") or "Sonstiges").strip()
        ergebnis[z.get("_cid")] = {
            "name": name, "art": KATEGORIE_ART.get(z.get("c1"), "kosten"), "farbe": farbe(z.get("c11")),
            "symbol": symbol_fuer(name), "uuid": z.get("c9") or "", "geloescht": _wahr(z.get("c8")),
        }
    return ergebnis


def eintraege(backup):
    """Logbuchzeilen als Felder für logbuch.Eintrag (ohne Fahrzeug und Kategorie)."""
    for z in backup.zeilen("lb.s"):
        fuellstand = _zahl(z.get("l27"))
        yield z.get("vid"), z.get("cid"), {
            "import_uuid": z.get("l9") or "",
            "zeitpunkt": zeitpunkt(z.get("l10")),
            "tachostand": _ganz(z.get("l11")),
            "kosten": _zahl(z.get("l12"), 2) or Decimal(0),
            "ort": (z.get("l23") or "")[:120],
            "beschreibung": z.get("l13") or "",
            # Tankfüllung: l26 Kraftstoff (0/1), l20 Menge, l27 Füllstand nach dem Tanken in %
            # (leer = voll), l22 vorherige Tankfüllung nicht erfasst, l25 Bordcomputer
            "kraftstoff_nr": 2 if z.get("l26") == "1" else 1,
            "menge": _zahl(z.get("l20"), 3) or None,
            "tank_voll": fuellstand is None or fuellstand >= 100,
            "vorherige_fehlt": _wahr(z.get("l22")),
            "bc_verbrauch": _zahl(z.get("l25"), 2),
            # Fahrt: l33 Start, l30 Tachostand Start, l31 Startort; Ziel steht in l23
            "start_zeitpunkt": zeitpunkt(z.get("l33")),
            "start_km": _ganz(z.get("l30")),
            "start_ort": (z.get("l31") or "")[:120],
        }


def erinnerungen(backup):
    for z in backup.zeilen("rm.s"):
        wiederholen = _wahr(z.get("r40"))
        jahre = _ganz(z.get("r43")) or 1
        # r20 erledigt; den Tag kennt das Backup nicht, nur die letzte Änderung (r0, Sekunden)
        erledigt = None
        if _wahr(z.get("r20")) and (z.get("r0") or "").isdigit():
            erledigt = tag(int(z["r0"]) * 1000)
        yield z.get("vid"), z.get("cid"), {
            "import_uuid": z.get("r9") or "",
            "notiz": (z.get("r30") or "")[:200],
            "faellig_am": tag(z.get("r10")),
            "faellig_km": _ganz(z.get("r11")),
            "wiederholen_monate": jahre * 12 if wiederholen else None,
            # r40 wiederholen, r43 alle … Jahre, r50 auch nach km, r52 alle … km
            "wiederholen_km": _ganz(z.get("r52")) if wiederholen and _wahr(z.get("r50")) else None,
            "erledigt_am": erledigt,
        }

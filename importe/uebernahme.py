"""Übernimmt ein gelesenes DriveNote-Backup in die Familie einer Person.

Jedes Fahrzeug im Backup wird entweder neu angelegt, einem vorhandenen Fahrzeug der
Familie zugeordnet (wenn zwei Personen dasselbe Auto in ihrer App führen) oder
ausgelassen. Einträge mit bekannter UUID werden aktualisiert; Einträge, die es im
Zielfahrzeug schon gibt (gleiche Kategorie, Zeit auf die Minute, Tachostand, Kosten),
und von einer anderen Person stammen, gelten als doppelt und werden übersprungen.
"""
import io
from dataclasses import dataclass, field
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction

from fahrzeuge.models import Fahrzeug
from logbuch.models import Eintrag, Erinnerung, Kategorie, Kategorieart

from . import drivenote

NEU = "neu"
AUSLASSEN = "aus"


@dataclass
class Bericht:
    fahrzeuge_neu: list = field(default_factory=list)
    fahrzeuge_zugeordnet: list = field(default_factory=list)
    kategorien_neu: list = field(default_factory=list)
    eintraege_neu: int = 0
    eintraege_aktualisiert: int = 0
    eintraege_doppelt: int = 0
    erinnerungen_neu: int = 0
    erinnerungen_aktualisiert: int = 0
    hinweise: list = field(default_factory=list)


def vorschlag(backup, familie):
    """Zuordnung je Fahrzeug im Backup: bekannte UUID, sonst gleiches Kennzeichen, sonst neu."""
    vorhandene = list(Fahrzeug.objects.filter(familie=familie))
    ergebnis = {}
    for fz in drivenote.fahrzeuge(backup):
        treffer = next((f for f in vorhandene if fz.uuid and f.import_uuid == fz.uuid), None)
        if treffer is None and fz.felder["kennzeichen"]:
            norm = _kennzeichen(fz.felder["kennzeichen"])
            treffer = next((f for f in vorhandene if f.kennzeichen and _kennzeichen(f.kennzeichen) == norm
                            and not f.verkauft and not fz.felder["verkauf_datum"]), None)
        ergebnis[fz.nr] = str(treffer.pk) if treffer else NEU if fz.eintraege else AUSLASSEN
    return ergebnis


def _kennzeichen(text):
    return "".join(c for c in text.upper() if c.isalnum())


def _foto(fahrzeug, daten):
    """Foto verkleinert speichern (max. 1600 px), damit Handys es schnell laden."""
    from PIL import Image, ImageOps
    try:
        bild = ImageOps.exif_transpose(Image.open(io.BytesIO(daten)))
        bild.thumbnail((1600, 1600))
        puffer = io.BytesIO()
        bild.convert("RGB").save(puffer, "JPEG", quality=85)
    except Exception:   # kaputtes Foto verhindert den Import nicht
        return
    fahrzeug.foto.save("foto.jpg", ContentFile(puffer.getvalue()), save=True)


def _kategorie(familie, daten, cache, bericht):
    """Kategorie der Familie zu einer Kategorie aus dem Backup."""
    if daten is None:
        return Kategorie.objects.get_or_create(familie=familie, name="Sonstiges",
                                               defaults={"symbol": "sonstiges"})[0]
    schluessel = daten["uuid"] or daten["name"]
    if schluessel in cache:
        return cache[schluessel]
    if daten["art"] != Kategorieart.KOSTEN:
        kat = Kategorie.fuer(familie, daten["art"])
    else:
        kat = (Kategorie.objects.filter(familie=familie, import_uuid=daten["uuid"]).first() if daten["uuid"] else None)
        if kat is None:
            kat = Kategorie.objects.filter(familie=familie, name__iexact=daten["name"]).first()
        if kat is None:
            kat = Kategorie.objects.create(familie=familie, name=daten["name"], art=Kategorieart.KOSTEN,
                                           farbe=daten["farbe"], symbol=daten["symbol"], import_uuid=daten["uuid"])
            bericht.kategorien_neu.append(kat.name)
        elif not kat.import_uuid and daten["uuid"]:
            kat.import_uuid = daten["uuid"]
            kat.save(update_fields=["import_uuid"])
    cache[schluessel] = kat
    return kat


def _doppelt(fahrzeug, kategorie, felder, person):
    """Gleicher Eintrag schon von jemand anderem erfasst? (Eigene Doppel aus der App bleiben, wie dort.)"""
    z = felder["zeitpunkt"]
    return Eintrag.objects.exclude(erfasst_von=person).filter(
        fahrzeug=fahrzeug, kategorie=kategorie, tachostand=felder["tachostand"], kosten=felder["kosten"],
        zeitpunkt__gte=z - timedelta(minutes=1), zeitpunkt__lte=z + timedelta(minutes=1),
    ).exists()


@transaction.atomic
def uebernehmen(backup, person, zuordnung):
    """zuordnung: {Fahrzeugnummer im Backup: "neu" | "aus" | Fahrzeug-ID der Familie}"""
    familie = person.familie
    bericht = Bericht()
    ziel = {}
    for fz in drivenote.fahrzeuge(backup):
        wahl = zuordnung.get(fz.nr, AUSLASSEN)
        if wahl == AUSLASSEN:
            continue
        if wahl == NEU:
            fahrzeug = Fahrzeug.objects.filter(familie=familie, import_uuid=fz.uuid).first() if fz.uuid else None
            if fahrzeug is None:
                fahrzeug = Fahrzeug.objects.create(familie=familie, halter=person, import_uuid=fz.uuid, **fz.felder)
                bericht.fahrzeuge_neu.append(str(fahrzeug))
                if fz.kraftstoff_unsicher:
                    bericht.hinweise.append(
                        f"{fahrzeug}: Kraftstoff „{fahrzeug.get_kraftstoff_display()}“ bitte prüfen.")
            else:
                bericht.fahrzeuge_zugeordnet.append(str(fahrzeug))
        else:
            fahrzeug = Fahrzeug.objects.get(familie=familie, pk=int(wahl))
            if not fahrzeug.import_uuid and fz.uuid:
                fahrzeug.import_uuid = fz.uuid
                fahrzeug.save(update_fields=["import_uuid"])
            # fehlende Stammdaten aus dem Backup ergänzen, vorhandene nicht überschreiben
            geaendert = [k for k, v in fz.felder.items() if v not in (None, "") and getattr(fahrzeug, k) in (None, "")]
            for k in geaendert:
                setattr(fahrzeug, k, fz.felder[k])
            if geaendert:
                fahrzeug.save(update_fields=geaendert)
            bericht.fahrzeuge_zugeordnet.append(str(fahrzeug))
        if fz.foto and not fahrzeug.foto:
            _foto(fahrzeug, fz.foto)
        ziel[fz.nr] = fahrzeug

    kategorien = drivenote.kategorien(backup)
    cache = {}
    for vid, cid, felder in drivenote.eintraege(backup):
        fahrzeug = ziel.get(vid)
        if fahrzeug is None or felder["zeitpunkt"] is None:
            continue
        kat = _kategorie(familie, kategorien.get(cid), cache, bericht)
        if kat.art != Kategorieart.TANKEN:
            felder.update(menge=None, tank_voll=True, vorherige_fehlt=False, bc_verbrauch=None, kraftstoff_nr=1)
        if kat.art != Kategorieart.FAHRT:
            felder.update(start_zeitpunkt=None, start_km=None, start_ort="")
        vorhanden = (Eintrag.objects.filter(fahrzeug__familie=familie, import_uuid=felder["import_uuid"]).first()
                     if felder["import_uuid"] else None)
        if vorhanden:
            for k, v in felder.items():
                setattr(vorhanden, k, v)
            vorhanden.fahrzeug, vorhanden.kategorie = fahrzeug, kat
            vorhanden.save()
            bericht.eintraege_aktualisiert += 1
        elif _doppelt(fahrzeug, kat, felder, person):
            bericht.eintraege_doppelt += 1
        else:
            Eintrag.objects.create(fahrzeug=fahrzeug, kategorie=kat, erfasst_von=person, **felder)
            bericht.eintraege_neu += 1

    for vid, cid, felder in drivenote.erinnerungen(backup):
        fahrzeug = ziel.get(vid)
        if fahrzeug is None:
            continue
        kat = _kategorie(familie, kategorien.get(cid), cache, bericht)
        vorhanden = (Erinnerung.objects.filter(fahrzeug__familie=familie, import_uuid=felder["import_uuid"]).first()
                     if felder["import_uuid"] else None)
        if vorhanden:
            for k, v in felder.items():
                setattr(vorhanden, k, v)
            vorhanden.fahrzeug, vorhanden.kategorie = fahrzeug, kat
            vorhanden.save()
            bericht.erinnerungen_aktualisiert += 1
        else:
            Erinnerung.objects.create(fahrzeug=fahrzeug, kategorie=kat, **felder)
            bericht.erinnerungen_neu += 1
    return bericht

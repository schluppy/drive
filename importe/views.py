"""DriveNote-Backup hochladen → Fahrzeuge zuordnen → übernehmen.

Das hochgeladene Backup liegt bis zur Übernahme unter media/import/ (Name zufällig,
in der Sitzung gemerkt) und wird danach gelöscht.
"""
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from fahrzeuge.models import Fahrzeug
from portal.zugriff import familie_noetig

from . import drivenote, uebernahme

ORDNER = Path(settings.MEDIA_ROOT) / "import"


def _datei(request):
    name = request.session.get("import_datei")
    if not name or "/" in name:
        return None
    pfad = ORDNER / name
    return pfad if pfad.exists() else None


@familie_noetig
def hochladen(request):
    if request.method == "POST":
        datei = request.FILES.get("backup")
        if datei is None:
            messages.error(request, "Bitte eine Backup-Datei auswählen.")
        elif datei.size > settings.IMPORT_MAX_MB * 1024 * 1024:
            messages.error(request, f"Die Datei ist größer als {settings.IMPORT_MAX_MB} MB.")
        else:
            ORDNER.mkdir(parents=True, exist_ok=True)
            alt = _datei(request)
            if alt:
                alt.unlink(missing_ok=True)
            name = f"{request.user.pk}-{secrets.token_hex(8)}.zip"
            with open(ORDNER / name, "wb") as ziel:
                for teil in datei.chunks():
                    ziel.write(teil)
            try:
                drivenote.lesen(ORDNER / name)
            except drivenote.BackupFehler as e:
                (ORDNER / name).unlink(missing_ok=True)
                messages.error(request, str(e))
                return redirect("importe:hochladen")
            request.session["import_datei"] = name
            return redirect("importe:zuordnen")
    return render(request, "importe/hochladen.html")


@familie_noetig
def zuordnen(request):
    pfad = _datei(request)
    if pfad is None:
        return redirect("importe:hochladen")
    backup = drivenote.lesen(pfad)
    familie = request.user.familie
    fahrzeuge = drivenote.fahrzeuge(backup)
    vorhandene = list(Fahrzeug.objects.filter(familie=familie))
    if request.method == "POST":
        if "abbrechen" in request.POST:
            pfad.unlink(missing_ok=True)
            request.session.pop("import_datei", None)
            return redirect("portal:start")
        erlaubt = {uebernahme.NEU, uebernahme.AUSLASSEN} | {str(f.pk) for f in vorhandene}
        wahl = {fz.nr: request.POST.get(f"fz{fz.nr}") for fz in fahrzeuge}
        wahl = {nr: w for nr, w in wahl.items() if w in erlaubt}
        bericht = uebernahme.uebernehmen(backup, request.user, wahl)
        pfad.unlink(missing_ok=True)
        request.session.pop("import_datei", None)
        return render(request, "importe/fertig.html", {"bericht": bericht})
    vorschlag = uebernahme.vorschlag(backup, familie)
    zeilen = [{"fz": fz, "wahl": vorschlag.get(fz.nr)} for fz in fahrzeuge]
    return render(request, "importe/zuordnen.html", {
        "zeilen": zeilen, "vorhandene": vorhandene, "meta": backup.meta,
        "anzahl": len(backup.zeilen("lb.s")), "erinnerungen": len(backup.zeilen("rm.s"))})

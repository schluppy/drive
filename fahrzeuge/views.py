from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from auswertung.kennzahlen import faelligkeiten, kennzahlen
from portal.zugriff import eigenes_fahrzeug, familie_noetig

from .forms import FahrzeugForm
from .models import Fahrzeug


@familie_noetig
def uebersicht(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    kz = kennzahlen(fahrzeug)
    faellig = faelligkeiten(fahrzeug, kz)
    fahrten = [e for e in kz.eintraege if e.kategorie.art == "fahrt"]
    return render(request, "fahrzeuge/uebersicht.html", {
        "fahrzeug": fahrzeug, "kz": kz, "naechste": faellig[0] if faellig else None,
        "fahrten": len(fahrten), "fahrten_km": sum(e.fahrtstrecke or 0 for e in fahrten), "tab": "fahrzeug",
    })


@familie_noetig
def liste(request):
    fahrzeuge = Fahrzeug.objects.filter(familie_id=request.user.familie_id).select_related("halter")
    zeilen = [(f, kennzahlen(f)) for f in fahrzeuge]
    return render(request, "fahrzeuge/liste.html", {"zeilen": zeilen})


@familie_noetig
def bearbeiten(request, fahrzeug_id=None):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id) if fahrzeug_id else Fahrzeug(
        familie_id=request.user.familie_id, halter=request.user)
    form = FahrzeugForm(request.POST or None, request.FILES or None, instance=fahrzeug,
                        familie=request.user.familie)
    if request.method == "POST" and form.is_valid():
        neu = fahrzeug.pk is None
        foto = form.cleaned_data.get("foto")
        fahrzeug = form.save(commit=False)
        if neu and foto:
            fahrzeug.foto = ""   # der Dateiname braucht die ID
        fahrzeug.save()
        if neu and foto:
            fahrzeug.foto = foto
            fahrzeug.save(update_fields=["foto"])
        messages.success(request, f"{fahrzeug} gespeichert.")
        return redirect(fahrzeug)
    return render(request, "fahrzeuge/bearbeiten.html", {"form": form, "fahrzeug": fahrzeug, "tab": "fahrzeug"})


@familie_noetig
def foto(request, fahrzeug_id):
    """Fotos nur für die eigene Familie – nicht öffentlich über /media/."""
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    if not fahrzeug.foto:
        raise Http404
    try:
        antwort = FileResponse(fahrzeug.foto.open("rb"), content_type="image/jpeg")
    except FileNotFoundError as e:
        raise Http404 from e
    antwort["Cache-Control"] = "private, max-age=86400"
    return antwort


@require_POST
@familie_noetig
def loeschen(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    if request.POST.get("bestaetigt") != str(fahrzeug):
        messages.error(request, "Zum Löschen den Namen des Fahrzeugs genau so eintragen.")
        return redirect("fahrzeuge:bearbeiten", fahrzeug.pk)
    name = str(fahrzeug)
    if fahrzeug.foto:
        fahrzeug.foto.delete(save=False)
    fahrzeug.delete()
    request.session.pop("fahrzeug", None)
    messages.success(request, f"{name} mit allen Einträgen gelöscht.")
    return redirect("portal:start")

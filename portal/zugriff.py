"""Trennung der Familien: jede Seite holt Fahrzeuge, Einträge und Kategorien nur
über diese Funktionen. Fremde IDs ergeben 404, nicht 403 – so verrät die Antwort nicht,
ob es das Fahrzeug gibt.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render


def familie_noetig(view):
    @login_required
    @wraps(view)
    def innen(request, *args, **kwargs):
        if request.user.familie_id is None:
            return render(request, "portal/ohne_familie.html", status=403)
        return view(request, *args, **kwargs)

    return innen


def eigenes_fahrzeug(request, fahrzeug_id):
    from fahrzeuge.models import Fahrzeug
    fahrzeug = get_object_or_404(Fahrzeug.objects.select_related("halter"),
                                 pk=fahrzeug_id, familie_id=request.user.familie_id)
    request.session["fahrzeug"] = fahrzeug.pk
    return fahrzeug


def eigener_eintrag(request, pk):
    from logbuch.models import Eintrag
    return get_object_or_404(Eintrag.objects.select_related("fahrzeug", "kategorie"),
                             pk=pk, fahrzeug__familie_id=request.user.familie_id)


def eigene_kategorien(request):
    from logbuch.models import Kategorie
    return Kategorie.objects.filter(familie_id=request.user.familie_id)

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from auswertung.kennzahlen import faelligkeiten, kennzahlen
from fahrzeuge.models import Fahrzeug
from konten.models import MagicLinkToken, Person

from . import mails
from .forms import EinladungForm, ProfilForm
from .zugriff import familie_noetig


def _ip(request):
    if settings.HINTER_PROXY and request.META.get("HTTP_X_REAL_IP"):
        return request.META["HTTP_X_REAL_IP"]
    return request.META.get("REMOTE_ADDR")


# --- Anmeldung per Einmal-Link ---------------------------------------------


def anmelden(request):
    if request.user.is_authenticated:
        return redirect("portal:start")
    ziel = request.GET.get("next") or request.POST.get("next") or ""
    if not url_has_allowed_host_and_scheme(ziel, allowed_hosts={request.get_host()}):
        ziel = ""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        person = Person.objects.filter(email=email, is_active=True).first()
        if person and not MagicLinkToken.zu_viele_anfragen(person, _ip(request)):
            mails.anmeldelink(person, ip=_ip(request), ziel=ziel)
        # Immer dieselbe Antwort – verrät nicht, welche Adressen hinterlegt sind.
        return redirect("portal:gesendet")
    return render(request, "portal/anmelden.html", {"next": ziel})


def gesendet(request):
    return render(request, "portal/gesendet.html", {"minuten": settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN})


def token(request, token):
    """GET zeigt nur einen Knopf: Mail-Programme, die Links vorab öffnen,
    verbrauchen den Einmal-Link so nicht."""
    eintrag = MagicLinkToken.finde_gueltig(token)
    if request.method == "POST":
        person = MagicLinkToken.einloesen(token)
        if person:
            login(request, person, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(eintrag.ziel if eintrag and eintrag.ziel else "portal:start")
        eintrag = None
    return render(request, "portal/token.html", {"eintrag": eintrag})


@require_POST
def abmelden(request):
    logout(request)
    return redirect("portal:anmelden")


def datenschutz(request):
    return render(request, "portal/datenschutz.html", {
        "betreiber": settings.BETREIBER_NAME, "kontakt": settings.BETREIBER_EMAIL})


def manifest(request):
    """Web-App-Manifest: „Zum Startbildschirm hinzufügen“ öffnet Drive wie eine App."""
    return HttpResponse(render_to_string("portal/manifest.webmanifest", request=request),
                        content_type="application/manifest+json")


# --- Start: alle Fahrzeuge der Familie --------------------------------------------


@familie_noetig
def start(request):
    fahrzeuge = Fahrzeug.objects.filter(familie_id=request.user.familie_id).select_related("halter")
    karten = []
    anstehend = []
    for f in fahrzeuge:
        kz = kennzahlen(f)
        karten.append({"f": f, "kz": kz})
        if not f.verkauft:
            for fl in faelligkeiten(f, kz):
                if fl.tage_bis is not None and fl.tage_bis <= 60 or fl.km_rest is not None and fl.km_rest <= 1500:
                    anstehend.append((f, fl))
    if not karten:
        return render(request, "portal/willkommen.html")
    aktiv = [k for k in karten if not k["f"].verkauft]
    verkauft = [k for k in karten if k["f"].verkauft]
    # eigene Fahrzeuge zuerst
    aktiv.sort(key=lambda k: (k["f"].halter_id != request.user.pk, str(k["f"])))
    anstehend.sort(key=lambda t: t[1].tage_bis if t[1].tage_bis is not None else 9999)
    return render(request, "portal/start.html", {"aktiv": aktiv, "verkauft": verkauft, "anstehend": anstehend})


# --- Familie: Mitglieder, Einladungen, eigenes Profil --------------------------------


@familie_noetig
def familie(request):
    form = EinladungForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        vorhanden = Person.objects.filter(email=email).first()
        if vorhanden and vorhanden.familie_id and vorhanden.familie_id != request.user.familie_id:
            form.add_error("email", "Diese Adresse gehört schon zu einer anderen Familie.")
        else:
            if vorhanden is None:
                vorhanden = Person.objects.create_user(email, form.cleaned_data["name"], familie=request.user.familie)
            elif vorhanden.familie_id is None:
                vorhanden.familie = request.user.familie
                vorhanden.save(update_fields=["familie"])
            mails.einladung(vorhanden, request.user, ip=_ip(request))
            messages.success(request, f"Einladung an {email} ist unterwegs.")
            return redirect("portal:familie")
    mitglieder = Person.objects.filter(familie_id=request.user.familie_id).order_by("name")
    return render(request, "portal/familie.html", {"form": form, "mitglieder": mitglieder})


@login_required
def profil(request):
    form = ProfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gespeichert.")
        return redirect("portal:profil")
    return render(request, "portal/profil.html", {"form": form})


def einladung_gueltigkeit():
    return timedelta(days=settings.EINLADUNG_GUELTIGKEIT_TAGE)

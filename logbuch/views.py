from datetime import date
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.db import models
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from auswertung.kennzahlen import eintraege_von, faelligkeiten, jahre, kennzahlen
from portal.templatetags.drive import deutsch
from portal.zugriff import eigene_kategorien, eigener_eintrag, eigenes_fahrzeug, familie_noetig

from . import verbrauch as vb
from .forms import (ErinnerungForm, ErledigtForm, FahrtForm, KategorieForm, KostenForm, OrtForm, SerieForm,
                    TankenForm, zeitpunkt_am)
from .models import Eintrag, Erinnerung, Kategorie, Kategorieart, Ort, Serie

MONATSNAMEN = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
               "November", "Dezember"]


def _jahr(request):
    try:
        return int(request.GET.get("jahr")) if request.GET.get("jahr") else None
    except ValueError:
        return None


# --- Logbuch ---------------------------------------------------------------------

@familie_noetig
def liste(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    eintraege = eintraege_von(fahrzeug)
    kz = kennzahlen(fahrzeug, eintraege)

    # Strecke seit dem vorigen Eintrag derselben Kategorie (bei Tankfüllungen: desselben Kraftstoffs)
    strecke = {}
    letzter = {}
    for e in sorted((e for e in eintraege if e.tachostand is not None), key=lambda e: (e.zeitpunkt, e.tachostand)):
        schluessel = (e.kategorie_id, e.kraftstoff_nr if e.kategorie.art == Kategorieart.TANKEN else 0)
        if schluessel in letzter and e.kategorie.art != Kategorieart.FAHRT:
            strecke[e.pk] = e.tachostand - letzter[schluessel]
        letzter[schluessel] = e.tachostand
    abschnitt_bis = {}
    gesamt = {}
    for k in kz.kraftstoffe:
        gesamt[k.nr] = k.verbrauch.gesamt
        for a in k.abschnitte:
            abschnitt_bis[a.bis.pk] = a

    kategorie_id = request.GET.get("kategorie")
    jahr = _jahr(request)
    sichtbar = [e for e in eintraege
                if (not kategorie_id or str(e.kategorie_id) == kategorie_id)
                and (jahr is None or timezone.localtime(e.zeitpunkt).year == jahr)]
    zeilen = []
    for e in sichtbar:
        a = abschnitt_bis.get(e.pk)
        trend = ""
        if a and gesamt.get(e.kraftstoff_nr) is not None and a.verbrauch is not None:
            trend = "hoch" if a.verbrauch > gesamt[e.kraftstoff_nr] else "runter"
        zeilen.append({"e": e, "strecke": e.fahrtstrecke if e.kategorie.art == Kategorieart.FAHRT else strecke.get(e.pk),
                       "abschnitt": a, "trend": trend})

    def monat(z):
        t = timezone.localtime(z["e"].zeitpunkt)
        return t.year, t.month

    monate = [{"titel": f"{MONATSNAMEN[m - 1]}{'' if j == date.today().year else f' {j}'}",
               "summe": sum(z["e"].kosten for z in gruppe),
               "zeilen": gruppe}
              for (j, m), gruppe in ((k, list(g)) for k, g in groupby(zeilen, key=monat))]
    kategorien = eigene_kategorien(request).filter(eintraege__fahrzeug=fahrzeug).distinct()
    return render(request, "logbuch/liste.html", {
        "fahrzeug": fahrzeug, "monate": monate, "kategorien": kategorien, "kategorie_id": kategorie_id,
        "jahre": jahre(eintraege), "jahr": jahr, "anzahl": len(sichtbar), "tab": "logbuch",
    })


FORMS = {Kategorieart.TANKEN: TankenForm, Kategorieart.FAHRT: FahrtForm, Kategorieart.KOSTEN: KostenForm}
TITEL = {Kategorieart.TANKEN: "Tankfüllung", Kategorieart.FAHRT: "Fahrt", Kategorieart.KOSTEN: "Logbucheintrag"}


def _form(art, request, fahrzeug, eintrag, initial=None):
    kwargs = {"fahrzeug": fahrzeug, "instance": eintrag, "initial": initial or {}}
    if art == Kategorieart.KOSTEN:
        kwargs["kategorien"] = eigene_kategorien(request)
    return FORMS[art](request.POST or None, **kwargs)


def _vorlage(art, form, fahrzeug, eintrag, extra=None):
    letzte = fahrzeug.eintraege.filter(tachostand__isnull=False).order_by("-zeitpunkt").first()
    return {"form": form, "fahrzeug": fahrzeug, "eintrag": eintrag, "art": art, "titel": TITEL[art],
            "orte": Ort.objects.filter(familie_id=fahrzeug.familie_id),
            "letzter_stand": letzte.tachostand if letzte else None, "tab": "logbuch", **(extra or {})}


@familie_noetig
def neu(request, fahrzeug_id, art):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    if art not in FORMS:
        return redirect("logbuch:liste", fahrzeug.pk)
    initial = {}
    erinnerung = None
    if art == Kategorieart.KOSTEN:
        kat = eigene_kategorien(request).filter(pk=request.GET.get("kategorie") or 0, art=art).first()
        if kat:
            initial["kategorie"] = kat
        erinnerung = Erinnerung.objects.filter(pk=request.GET.get("erinnerung") or 0, fahrzeug=fahrzeug).first()
        if erinnerung:
            initial.update(kategorie=erinnerung.kategorie, beschreibung=erinnerung.notiz)
    if art == Kategorieart.FAHRT:
        # Start = höchster bekannter Stand und Ziel der letzten Fahrt
        hoechster = fahrzeug.eintraege.filter(tachostand__isnull=False).order_by("-tachostand").first()
        letzte_fahrt = fahrzeug.eintraege.filter(kategorie__art=Kategorieart.FAHRT, ort__isnull=False).select_related(
            "ort").order_by("-zeitpunkt").first()
        if hoechster:
            initial["start_km"] = hoechster.tachostand
        if letzte_fahrt:
            initial["start_ort_name"] = letzte_fahrt.ort.name
    if art == Kategorieart.TANKEN and len(fahrzeug.kraftstoffe) > 1 and request.GET.get("kraftstoff") == "2":
        initial["kraftstoff_nr"] = 2
    eintrag = Eintrag(fahrzeug=fahrzeug, kategorie=Kategorie.fuer(request.user.familie, art)
                      if art != Kategorieart.KOSTEN else None, erfasst_von=request.user)
    form = _form(art, request, fahrzeug, eintrag, initial)
    if request.method == "POST" and form.is_valid():
        eintrag = form.save()
        if erinnerung and not erinnerung.erledigt_am:
            _erledigen(erinnerung, timezone.localtime(eintrag.zeitpunkt).date(), eintrag.tachostand)
            messages.success(request, f"Erinnerung „{erinnerung}“ erledigt.")
        messages.success(request, f"{TITEL[art]} gespeichert{_verbrauchstext(eintrag)}.")
        return redirect("logbuch:liste", fahrzeug.pk)
    return render(request, "logbuch/formular.html", _vorlage(art, form, fahrzeug, eintrag,
                                                              {"erinnerung": erinnerung}))


def _verbrauchstext(eintrag):
    """„… – 6,8 l/100 km auf 612 km“ direkt nach dem Speichern einer vollen Tankfüllung."""
    if not eintrag.ist_tanken or not eintrag.tank_voll:
        return ""
    abschnitte = vb.abschnitte(vb.tankfuellungen(eintrag.fahrzeug, eintrag.kraftstoff_nr))
    a = next((a for a in abschnitte if a.bis.pk == eintrag.pk), None)
    if a is None or a.verbrauch is None:
        return ""
    return (f" – {deutsch(a.verbrauch, 2)} {eintrag.fahrzeug.einheit(eintrag.kraftstoff_nr)}/100 km "
            f"auf {deutsch(a.km)} km")


@familie_noetig
def bearbeiten(request, pk):
    eintrag = eigener_eintrag(request, pk)
    fahrzeug = eigenes_fahrzeug(request, eintrag.fahrzeug_id)
    art = eintrag.kategorie.art
    form = _form(art, request, fahrzeug, eintrag)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{TITEL[art]} gespeichert.")
        return redirect(reverse("logbuch:liste", args=[fahrzeug.pk]) + f"#e{eintrag.pk}")
    return render(request, "logbuch/formular.html", _vorlage(art, form, fahrzeug, eintrag))


@require_POST
@familie_noetig
def loeschen(request, pk):
    eintrag = eigener_eintrag(request, pk)
    fahrzeug_id = eintrag.fahrzeug_id
    eintrag.delete()
    messages.success(request, "Eintrag gelöscht.")
    return redirect("logbuch:liste", fahrzeug_id)


# --- Serien ---------------------------------------------------------------------

@familie_noetig
def serien(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    liste_ = fahrzeug.serien.select_related("kategorie").annotate(gebucht=Count("eintraege"))
    return render(request, "logbuch/serien.html", {"fahrzeug": fahrzeug, "serien": liste_, "tab": "logbuch"})


@familie_noetig
def serie_bearbeiten(request, fahrzeug_id, pk=None):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    serie = get_object_or_404(Serie, pk=pk, fahrzeug=fahrzeug) if pk else Serie(
        fahrzeug=fahrzeug, angelegt_von=request.user, beginn=date.today())
    form = SerieForm(request.POST or None, instance=serie, kategorien=eigene_kategorien(request))
    if request.method == "POST":
        if "loeschen" in request.POST and serie.pk:
            serie.delete()
            messages.success(request, "Serie gelöscht; gebuchte Einträge bleiben im Logbuch.")
            return redirect("logbuch:serien", fahrzeug.pk)
        if form.is_valid():
            serie = form.save()
            from .serien import buchen
            n = buchen(serie)
            messages.success(request, f"Serie gespeichert{f', {n} Einträge gebucht' if n else ''}.")
            return redirect("logbuch:serien", fahrzeug.pk)
    return render(request, "logbuch/serie.html", {"form": form, "fahrzeug": fahrzeug, "serie": serie,
                                                  "tab": "logbuch"})


# --- Erinnerungen ---------------------------------------------------------------

@familie_noetig
def erinnerungen(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    kz = kennzahlen(fahrzeug)
    erledigt = fahrzeug.erinnerungen.filter(erledigt_am__isnull=False).select_related("kategorie").order_by(
        "-erledigt_am")[:20]
    return render(request, "logbuch/erinnerungen.html", {
        "fahrzeug": fahrzeug, "geplant": faelligkeiten(fahrzeug, kz), "erledigt": erledigt,
        "tachostand": kz.tachostand, "tab": "erinnerungen",
        "tage_vorher": settings.ERINNERUNG_TAGE_VORHER, "km_vorher": settings.ERINNERUNG_KM_VORHER})


@familie_noetig
def erinnerung_bearbeiten(request, fahrzeug_id, pk=None):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    erinnerung = get_object_or_404(Erinnerung, pk=pk, fahrzeug=fahrzeug) if pk else Erinnerung(fahrzeug=fahrzeug)
    form = ErinnerungForm(request.POST or None, instance=erinnerung, kategorien=eigene_kategorien(request))
    if request.method == "POST":
        if "loeschen" in request.POST and erinnerung.pk:
            erinnerung.delete()
            messages.success(request, "Erinnerung gelöscht.")
            return redirect("logbuch:erinnerungen", fahrzeug.pk)
        if form.is_valid():
            erinnerung = form.save(commit=False)
            erinnerung.mail_gesendet_am = None   # neue Fälligkeit → neue Mail
            erinnerung.save()
            messages.success(request, "Erinnerung gespeichert.")
            return redirect("logbuch:erinnerungen", fahrzeug.pk)
    return render(request, "logbuch/erinnerung.html", {"form": form, "fahrzeug": fahrzeug,
                                                       "erinnerung": erinnerung, "tab": "erinnerungen"})


def _erledigen(erinnerung, datum, tachostand):
    erinnerung.erledigt_am = datum
    erinnerung.save(update_fields=["erledigt_am"])
    if erinnerung.wiederkehrend:
        erinnerung.naechste(datum, tachostand).save()


@familie_noetig
def erinnerung_erledigt(request, fahrzeug_id, pk):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    erinnerung = get_object_or_404(Erinnerung, pk=pk, fahrzeug=fahrzeug, erledigt_am__isnull=True)
    kz = kennzahlen(fahrzeug)
    form = ErledigtForm(request.POST or None, initial={"datum": date.today(), "tachostand": kz.tachostand})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if d["kosten"]:
            Eintrag.objects.create(fahrzeug=fahrzeug, kategorie=erinnerung.kategorie, zeitpunkt=zeitpunkt_am(d["datum"]),
                                   tachostand=d["tachostand"], kosten=d["kosten"],
                                   ort=Ort.holen(request.user.familie, d["ort"]),
                                   beschreibung=erinnerung.notiz, erfasst_von=request.user)
        _erledigen(erinnerung, d["datum"], d["tachostand"])
        messages.success(request, f"„{erinnerung}“ erledigt"
                         + (" – die nächste ist eingetragen." if erinnerung.wiederkehrend else "."))
        return redirect("logbuch:erinnerungen", fahrzeug.pk)
    return render(request, "logbuch/erledigt.html", {"form": form, "fahrzeug": fahrzeug, "erinnerung": erinnerung,
                                                     "orte": Ort.objects.filter(familie_id=fahrzeug.familie_id),
                                                     "tab": "erinnerungen"})


# --- Kategorien (je Familie) ----------------------------------------------------------

@familie_noetig
def kategorien(request):
    liste_ = eigene_kategorien(request).annotate(
        n_eintraege=Count("eintraege", distinct=True),
        n_erinnerungen=Count("erinnerungen", distinct=True))
    return render(request, "logbuch/kategorien.html", {"kategorien": liste_})


@familie_noetig
def kategorie_bearbeiten(request, pk=None):
    kat = get_object_or_404(eigene_kategorien(request), pk=pk) if pk else Kategorie(
        familie=request.user.familie, art=Kategorieart.KOSTEN)
    form = KategorieForm(request.POST or None, instance=kat)
    if request.method == "POST":
        if "loeschen" in request.POST and kat.pk and not kat.geschuetzt:
            try:
                kat.delete()
                messages.success(request, f"Kategorie „{kat}“ gelöscht.")
            except ProtectedError:
                messages.error(request, f"„{kat}“ hat noch Einträge oder Erinnerungen und bleibt.")
            return redirect("logbuch:kategorien")
        if form.is_valid():
            if Kategorie.objects.filter(familie=request.user.familie, name__iexact=form.cleaned_data["name"]
                                        ).exclude(pk=kat.pk).exists():
                form.add_error("name", "Diese Kategorie gibt es schon.")
            else:
                form.save()
                messages.success(request, "Kategorie gespeichert.")
                return redirect("logbuch:kategorien")
    return render(request, "logbuch/kategorie.html", {"form": form, "kategorie": kat})


# --- Orte (je Familie) -----------------------------------------------------------------

@familie_noetig
def orte(request):
    liste_ = Ort.objects.filter(familie_id=request.user.familie_id).annotate(
        n_ziel=Count("eintraege", distinct=True), n_start=Count("fahrtstarts", distinct=True))
    return render(request, "logbuch/orte.html", {"orte": liste_})


@familie_noetig
def ort_bearbeiten(request, pk):
    ort = get_object_or_404(Ort, pk=pk, familie_id=request.user.familie_id)
    form = OrtForm(request.POST or None, instance=ort)
    if request.method == "POST":
        if "loeschen" in request.POST:
            if ort.anzahl:
                messages.error(request, f"„{ort}“ steht noch in {ort.anzahl} Einträgen – umbenennen oder zusammenführen.")
                return redirect("logbuch:ort", ort.pk)
            ort.delete()
            messages.success(request, f"„{ort}“ gelöscht.")
            return redirect("logbuch:orte")
        if form.is_valid():
            name = form.cleaned_data["name"]
            anderer = Ort.objects.filter(familie_id=request.user.familie_id, name__iexact=name).exclude(pk=ort.pk).first()
            if anderer:
                n = ort.anzahl
                ort.zusammenfuehren(anderer)
                messages.success(request, f"Mit „{anderer}“ zusammengeführt ({n} Einträge).")
            else:
                Ort.objects.filter(pk=ort.pk).update(name=name)
                messages.success(request, f"In „{name}“ umbenannt – in allen Einträgen.")
            return redirect("logbuch:orte")
    eintraege = (Eintrag.objects.filter(fahrzeug__familie_id=request.user.familie_id)
                 .filter(models.Q(ort=ort) | models.Q(start_ort=ort))
                 .select_related("fahrzeug", "kategorie").order_by("-zeitpunkt")[:30])
    return render(request, "logbuch/ort.html", {"form": form, "ort": ort, "eintraege": eintraege})

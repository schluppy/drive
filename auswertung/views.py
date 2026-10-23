from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from fahrzeuge.models import Fahrzeug
from konten.models import PERSONENFARBEN
from logbuch import verbrauch as vb
from portal.zugriff import eigenes_fahrzeug, familie_noetig

from . import diagramme as dg
from .kennzahlen import eintraege_von, jahre, kennzahlen, kosten_nach_kategorie

MONATE = dg.MONATE


def _jahr(request):
    try:
        return int(request.GET.get("jahr")) if request.GET.get("jahr") else None
    except ValueError:
        return None


@familie_noetig
def statistik(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    eintraege = eintraege_von(fahrzeug)
    jahr = _jahr(request)
    kz = kennzahlen(fahrzeug, eintraege, jahr)
    alle_jahre = jahre(eintraege)

    kraftstoffe = []
    for k in kz.kraftstoffe:
        werte = [a.verbrauch for a in k.abschnitte if a.verbrauch is not None]
        diagramm = dg.linien([
            {"name": "Verbrauch", "farbe": "var(--blau)",
             "punkte": [(a.datum, a.verbrauch, f"{a.datum:%d.%m.%y}: {dg.deutsch(a.verbrauch, 2)} {k.einheit}/100 km "
                         f"auf {dg.deutsch(a.km)} km") for a in k.abschnitte]},
            {"name": "Bordcomputer", "farbe": "var(--orange)", "gestrichelt": True,
             "punkte": [(a.datum, a.bc, None) for a in k.abschnitte if a.bc]},
        ], einheit=f"{k.einheit}/100", stellen_wert=2)
        preise = [(timezone.localtime(f.zeitpunkt).date(), f.preis_je_einheit) for f in k.fuellungen
                  if f.preis_je_einheit]
        preis_diagramm = dg.linien([{"name": f"Preis je {k.einheit}", "farbe": "var(--gruen)",
                                     "punkte": [(d, p, None) for d, p in preise]}],
                                   einheit=f"€/{k.einheit}", stellen_wert=3)
        reichweite = dg.linien([{"name": "Strecke je Tankfüllung", "farbe": "var(--lila)",
                                 "punkte": [(a.datum, a.km, f"{a.datum:%d.%m.%y}: {dg.deutsch(a.km)} km mit "
                                             f"{dg.deutsch(a.menge, 2)} {k.einheit}") for a in k.abschnitte]}],
                               einheit="km", stellen_wert=0, null_basis=True)
        # je Jahr
        je_jahr = []
        alle = vb.abschnitte(vb.tankfuellungen(fahrzeug, k.nr, eintraege))
        for j in (alle_jahre if jahr is None else [jahr]):
            ab = vb.im_zeitraum(alle, j)
            v = vb.verbrauch(ab)
            fj = [f for f in vb.tankfuellungen(fahrzeug, k.nr, eintraege) if timezone.localtime(f.zeitpunkt).year == j]
            menge = sum((f.menge for f in fj), Decimal(0))
            kosten = sum((f.kosten for f in fj), Decimal(0))
            if fj or ab:
                je_jahr.append({"jahr": j, "v": v, "menge": menge, "kosten": kosten,
                                "preis": kosten / menge if menge else None, "anzahl": len(fj)})
        kraftstoffe.append({
            "k": k, "diagramm": diagramm, "preis_diagramm": preis_diagramm, "reichweite": reichweite,
            "min": min(werte) if werte else None, "max": max(werte) if werte else None,
            "preis_min": min((p for _, p in preise), default=None), "preis_max": max((p for _, p in preise), default=None),
            "preis_schnitt": k.kosten_gesamt / k.menge_gesamt if k.menge_gesamt else None,
            "weiteste": max(k.abschnitte, key=lambda a: a.km, default=None),
            "je_jahr": je_jahr,
        })

    # Fahrleistung
    jf = vb.jahresfahrleistung(fahrzeug, eintraege)
    if jahr is None:
        fl_beschr = [str(j) for j in sorted(jf)]
        fl_werte = [jf[j] for j in sorted(jf)]
    else:
        fl_beschr, fl_werte = MONATE, _monatsfahrleistung(fahrzeug, eintraege, jahr)
    fahrleistung = dg.balken(fl_beschr, [{"name": "Fahrleistung", "farbe": "var(--blau)", "werte": fl_werte}],
                             einheit="km")
    liste = vb.mit_tachostand(e for e in eintraege
                              if jahr is None or timezone.localtime(e.zeitpunkt).year == jahr)
    tacho = dg.linien([{"name": "Tachostand", "farbe": "var(--blau)",
                        "punkte": [(timezone.localtime(e.zeitpunkt).date(), e.tachostand, None) for e in liste]}],
                      einheit="km", stellen_wert=0, flaeche=True)
    return render(request, "auswertung/statistik.html", {
        "fahrzeug": fahrzeug, "kz": kz, "jahr": jahr, "jahre": alle_jahre, "kraftstoffe": kraftstoffe,
        "fahrleistung": fahrleistung, "tacho": tacho, "jahresfahrleistung": sorted(jf.items(), reverse=True),
        "tab": "statistik",
    })


def _monatsfahrleistung(fahrzeug, eintraege, jahr):
    liste = vb.mit_tachostand(eintraege)
    stand_ende = {}
    vorher = None
    for e in liste:
        t = timezone.localtime(e.zeitpunkt)
        if t.year < jahr:
            vorher = max(vorher or 0, e.tachostand)
        elif t.year == jahr:
            stand_ende[t.month] = max(stand_ende.get(t.month, 0), e.tachostand)
    if vorher is None:
        vorher = vb.start_tachostand(fahrzeug, liste) or 0
    werte = []
    for m in range(1, 13):
        if m in stand_ende:
            stand = max(stand_ende[m], vorher)
            werte.append(stand - vorher)
            vorher = stand
        else:
            werte.append(0)
    return werte


@familie_noetig
def kosten(request, fahrzeug_id):
    fahrzeug = eigenes_fahrzeug(request, fahrzeug_id)
    eintraege = eintraege_von(fahrzeug)
    jahr = _jahr(request)
    alle_jahre = jahre(eintraege)
    nach_kat = kosten_nach_kategorie(eintraege, jahr)
    summe = sum((s for _, _, s in nach_kat), Decimal(0))
    ring = dg.ring([(k.name, k.farbe, s) for k, _, s in nach_kat], gesamt_text=f"{dg.deutsch(summe, 0)} €")

    kats = [k for k, _, _ in nach_kat]
    if jahr is None:
        spalten = sorted(alle_jahre)
        beschr = [str(j) for j in spalten]

        def spalte(e):
            return timezone.localtime(e.zeitpunkt).year
    else:
        spalten = list(range(1, 13))
        beschr = MONATE

        def spalte(e):
            t = timezone.localtime(e.zeitpunkt)
            return t.month if t.year == jahr else None
    tabelle = defaultdict(lambda: defaultdict(Decimal))
    for e in eintraege:
        s = spalte(e)
        if s is not None and e.kosten:
            tabelle[e.kategorie_id][s] += e.kosten
    stapel = [{"name": k.name, "farbe": k.farbe, "werte": [tabelle[k.pk][s] for s in spalten]} for k in kats]
    entwicklung = dg.balken(beschr, stapel, einheit="€")

    jf = vb.jahresfahrleistung(fahrzeug, eintraege)
    je_jahr = []
    for j in (alle_jahre if jahr is None else [jahr]):
        s = sum((e.kosten for e in eintraege if timezone.localtime(e.zeitpunkt).year == j), Decimal(0))
        kmj = jf.get(j, 0)
        monate = 12 if j != date.today().year else date.today().month
        je_jahr.append({"jahr": j, "summe": s, "monat": s / monate, "km": kmj, "je_km": s / kmj if kmj else None})

    # Kosten pro km kumuliert
    start = vb.start_tachostand(fahrzeug, eintraege)
    punkte = []
    summe_bisher = Decimal(0)
    for e in sorted(eintraege, key=lambda e: e.zeitpunkt):
        summe_bisher += e.kosten
        if e.tachostand is not None and start is not None and e.tachostand - start >= 500:
            t = timezone.localtime(e.zeitpunkt).date()
            if jahr is None or t.year == jahr:
                punkte.append((t, summe_bisher / (e.tachostand - start), None))
    kumuliert = dg.linien([{"name": "Kosten pro km", "farbe": "var(--blau)", "punkte": punkte}],
                          einheit="€/km", stellen_wert=3)
    kz = kennzahlen(fahrzeug, eintraege, jahr)
    return render(request, "auswertung/kosten.html", {
        "fahrzeug": fahrzeug, "jahr": jahr, "jahre": alle_jahre, "nach_kat": nach_kat, "summe": summe,
        "ring": ring, "entwicklung": entwicklung, "je_jahr": je_jahr, "kumuliert": kumuliert, "kz": kz,
        "tab": "kosten",
    })


# --- Familienvergleich ------------------------------------------------------------


def _personenzeile():
    return {"km": 0, "menge": Decimal(0), "kosten": Decimal(0), "abschnitte": [], "fahrzeuge": set()}


@familie_noetig
def vergleich(request):
    """Wer fährt am sparsamsten, wer kommt mit einer Tankfüllung am weitesten?

    Gezählt wird der Hauptkraftstoff; jeder Abschnitt (voll bis voll) gehört der Person,
    die die Tankfüllung am Ende eingetragen hat – so zählt bei geteilten Autos jede
    Tankfüllung für die Person, die den Tank leer gefahren hat."""
    jahr = _jahr(request)
    fahrzeuge = Fahrzeug.objects.filter(familie_id=request.user.familie_id, im_vergleich=True
                                        ).exclude(kraftstoff="").select_related("halter")
    zeilen = []
    personen = defaultdict(_personenzeile)
    alle_jahre = set()
    for f in fahrzeuge:
        eintraege = eintraege_von(f)
        alle_jahre |= set(jahre(eintraege))
        kz = kennzahlen(f, eintraege, jahr)
        k = kz.kraftstoff(1)
        if k is None or not k.abschnitte:
            continue
        v = k.verbrauch
        zeilen.append({
            "fahrzeug": f, "einheit": k.einheit, "kraftstoff": k.name, "v": v,
            "bester": min(k.abschnitte, key=lambda a: a.verbrauch),
            "weiteste": max(k.abschnitte, key=lambda a: a.km),
            "preis": k.kosten_gesamt / k.menge_gesamt if k.menge_gesamt else None,
            "fahrleistung": kz.fahrleistung, "kosten_je_km": kz.kosten_je_km,
        })
        for a in k.abschnitte:
            p = personen[(a.person, k.einheit)]
            p["km"] += a.km
            p["menge"] += a.menge
            p["kosten"] += a.kosten
            p["abschnitte"].append(a)
            p["fahrzeuge"].add(f)

    personenzeilen = []
    for (person, einheit), p in personen.items():
        ab = p["abschnitte"]
        personenzeilen.append({
            "person": person, "einheit": einheit, "km": p["km"], "anzahl": len(ab),
            "verbrauch": p["menge"] / p["km"] * 100 if p["km"] else None,
            "preis": p["kosten"] / p["menge"] if p["menge"] else None,
            "bester": min(ab, key=lambda a: a.verbrauch), "weiteste": max(ab, key=lambda a: a.km),
            "fahrzeuge": sorted(p["fahrzeuge"], key=str),
        })
    personenzeilen.sort(key=lambda z: (z["einheit"], z["verbrauch"] or 999))
    zeilen.sort(key=lambda z: (z["einheit"], z["v"].gesamt or 999))
    for i, z in enumerate(zeilen):
        z["farbe"] = PERSONENFARBEN[i % len(PERSONENFARBEN)]

    def bester(liste, schluessel, umgekehrt=False):
        kandidaten = [z for z in liste if schluessel(z) is not None and z["einheit"] == "l"]
        if not kandidaten:
            return None
        return (max if umgekehrt else min)(kandidaten, key=schluessel)

    bestenliste = {
        "sparsam": bester(zeilen, lambda z: z["v"].gesamt),
        "weiteste": bester(zeilen, lambda z: z["weiteste"].km, umgekehrt=True),
        "beste_fuellung": bester(zeilen, lambda z: z["bester"].verbrauch),
        "guenstig": bester(zeilen, lambda z: z["preis"]),
        "vielfahrer": bester(zeilen, lambda z: z["fahrleistung"], umgekehrt=True),
    }
    return render(request, "auswertung/vergleich.html", {
        "jahr": jahr, "jahre": sorted(alle_jahre, reverse=True), "zeilen": zeilen, "personen": personenzeilen,
        "beste": bestenliste, "diagramm": _vergleichsdiagramm(zeilen, jahr),
    })


def _vergleichsdiagramm(zeilen, jahr):
    """Verbrauch je Fahrzeug im Monats- (Jahr) bzw. Quartalsmittel (Gesamt), nach Strecke gewichtet."""
    serien = []
    for z in zeilen:
        if z["einheit"] != "l":
            continue
        k = next(k for k in kennzahlen(z["fahrzeug"], jahr=jahr).kraftstoffe if k.nr == 1)
        gruppen = defaultdict(list)
        for a in k.abschnitte:
            schluessel = (a.datum.year, a.datum.month if jahr else (a.datum.month - 1) // 3 * 3 + 1)
            gruppen[schluessel].append(a)
        punkte = []
        for (j, m), ab in sorted(gruppen.items()):
            v = vb.verbrauch(ab)
            punkte.append((date(j, m, 15), v.gesamt,
                           f"{z['fahrzeug']} {MONATE[m - 1]} {j}: {dg.deutsch(v.gesamt, 2)} l/100 km"))
        halter = z["fahrzeug"].halter
        serien.append({"name": f"{halter.vorname if halter else ''} {z['fahrzeug']}".strip(),
                       "farbe": z["farbe"], "punkte": punkte})
    return dg.linien(serien, einheit="l/100", stellen_wert=2), serien

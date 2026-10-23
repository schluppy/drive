"""Zahlen deutsch formatiert: 1.234,56 €, 96.222 km, 10,395 l/100 km."""
from datetime import date
from decimal import Decimal

from django import template
from django.utils.html import format_html

register = template.Library()


def deutsch(zahl, stellen=0):
    text = f"{Decimal(zahl):,.{stellen}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


@register.filter
def euro(betrag, stellen=2):
    if betrag is None or betrag == "":
        return "–"
    return f"{deutsch(betrag, int(stellen))} €"


@register.filter
def km(wert):
    if wert is None or wert == "":
        return "–"
    return f"{deutsch(wert, 0)} km"


@register.filter
def zahl(wert, stellen=0):
    if wert is None or wert == "":
        return "–"
    return deutsch(wert, int(stellen))


@register.filter
def vorzeichen(wert, stellen=0):
    """+778 bzw. −12"""
    if wert is None:
        return ""
    return ("+" if wert >= 0 else "−") + deutsch(abs(wert), int(stellen))


@register.filter
def zeitraum(tage, ab=None):
    """Tage ab heute → „+1 Jahr, 3 Monate, 9 Tage“ wie in DriveNote (nach Kalender)."""
    if tage is None:
        return ""
    from datetime import timedelta
    heute = ab or date.today()
    ziel = heute + timedelta(days=int(tage))
    if ziel >= heute:
        return "+" + alter(heute, ziel, ohne_null=True)
    return "−" + alter(ziel, heute, ohne_null=True)


@register.filter
def alter(von, bis=None, ohne_null=False):
    """Datum → „7 Jahre, 1 Monat, 10 Tage“ (genau nach Kalender)."""
    if not von:
        return "–"
    bis = bis or date.today()
    jahre = bis.year - von.year
    monate = bis.month - von.month
    tage = bis.day - von.day
    if tage < 0:
        monate -= 1
        vormonat = date(bis.year, bis.month, 1).toordinal() - 1
        tage += date.fromordinal(vormonat).day
    if monate < 0:
        jahre -= 1
        monate += 12
    teile = []
    if jahre:
        teile.append(f"{jahre} Jahr" + ("e" if jahre != 1 else ""))
    if monate:
        teile.append(f"{monate} Monat" + ("e" if monate != 1 else ""))
    if tage or not teile or not ohne_null:
        teile.append(f"{tage} Tag" + ("e" if tage != 1 else ""))
    return ", ".join(teile)


@register.simple_tag
def kategorie_marke(kategorie):
    return format_html('<span class="kat-symbol" style="--kat:{}" aria-hidden="true">{}</span>',
                       kategorie.farbe, kategorie.zeichen)


@register.filter
def dauer(wert):
    """timedelta → „6:34 h“"""
    if not wert:
        return "–"
    minuten = int(wert.total_seconds() // 60)
    return f"{minuten // 60}:{minuten % 60:02d} h"


@register.filter
def wechsel(pfad, fahrzeug_id):
    """Gleiche Seite für ein anderes Fahrzeug (Auswahl im Kopf); Formulare → Logbuch bzw. Übersicht."""
    import re
    m = re.match(r"^/(fahrzeug|logbuch|auswertung)/(\d+)/(statistik/|kosten/|erinnerungen/|serien/)?(neu/)?", pfad)
    if not m:
        return f"/fahrzeug/{fahrzeug_id}/"
    return f"/{m.group(1)}/{fahrzeug_id}/{m.group(3) or ''}"


@register.filter
def sub(a, b):
    if a is None or b is None:
        return None
    return a - b


@register.filter
def teile(a, b):
    if a is None or not b:
        return None
    return Decimal(a) / Decimal(b)


@register.filter
def mal(a, b):
    if a is None or b is None:
        return None
    return Decimal(a) * Decimal(b)


@register.filter
def anteil(teil, ganzes):
    """Prozent"""
    if not ganzes or teil is None:
        return None
    return Decimal(teil) / Decimal(ganzes) * 100


@register.filter
def summe_anzahl(zeilen):
    return sum(n for _k, n, _s in zeilen)

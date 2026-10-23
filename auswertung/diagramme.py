"""Diagramme als SVG, auf dem Server gezeichnet – kein JavaScript, keine Bibliothek.

Alle Funktionen geben fertiges, sicheres SVG (mark_safe nach escape) zurück. Die Breite
passt sich über viewBox an; Schrift und Linien nehmen die Farben der Seite (CSS-Variablen).
Jeder Punkt und Balken hat einen <title> – auf dem Handy per Antippen, am Rechner per Maus.
"""
import math
from datetime import date
from decimal import Decimal

from django.utils.html import escape
from django.utils.safestring import mark_safe

from portal.templatetags.drive import deutsch

B, H = 460, 230          # Zeichenfläche (schmal, damit die Schrift auf dem Handy lesbar bleibt)
L, R, O, U = 44, 10, 24, 26   # Ränder links, rechts, oben, unten
MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _schoene_schritte(lo, hi, anzahl=4):
    if hi <= lo:
        hi = lo + 1
    roh = (hi - lo) / anzahl
    potenz = 10 ** math.floor(math.log10(roh))
    for f in (1, 2, 2.5, 5, 10):
        if roh <= f * potenz:
            schritt = f * potenz
            break
    start = math.floor(lo / schritt) * schritt
    ende = math.ceil(hi / schritt) * schritt
    werte = []
    v = start
    while v <= ende + schritt / 1000:
        werte.append(v)
        v += schritt
    return werte, schritt


def _stellen(schritt):
    return 0 if schritt >= 1 else 1 if schritt >= 0.1 else 2 if schritt >= 0.01 else 3


def _rahmen(hoehe, inhalt, beschriftung):
    return mark_safe(
        f'<svg class="diagramm" viewBox="0 0 {B} {hoehe}" role="img" aria-label="{escape(beschriftung)}" '
        f'preserveAspectRatio="xMidYMid meet">{inhalt}</svg>')


def _y_achse(ticks, y, stellen, einheit):
    teile = []
    for t in ticks:
        yy = y(t)
        teile.append(f'<line class="gitter" x1="{L}" x2="{B - R}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        teile.append(f'<text class="achse" x="{L - 6}" y="{yy + 4:.1f}" text-anchor="end">'
                     f'{deutsch(t, stellen)}</text>')
    if einheit:
        teile.append(f'<text class="achse" x="4" y="13" text-anchor="start">{escape(einheit)}</text>')
    return "".join(teile)


def leer(text="Noch keine Daten"):
    return mark_safe(f'<p class="leise diagramm-leer">{escape(text)}</p>')


def linien(serien, einheit="", stellen_wert=2, hoehe=H, flaeche=False, null_basis=False):
    """serien: [{"name", "farbe", "punkte": [(date, Zahl, Titel oder None)], "gestrichelt": bool}]"""
    punkte = [p for s in serien for p in s["punkte"] if p[1] is not None]
    if len(punkte) < 2:
        return leer()
    x0 = min(p[0] for p in punkte).toordinal()
    x1 = max(p[0] for p in punkte).toordinal()
    if x1 == x0:
        x1 = x0 + 1
    werte = [float(p[1]) for p in punkte]
    lo, hi = (0 if null_basis else min(werte)), max(werte)
    if not null_basis:
        spanne = (hi - lo) or abs(hi) or 1
        lo = max(lo - spanne * 0.08, 0) if lo >= 0 else lo - spanne * 0.08   # keine negative Achse für km, €, l
        hi += spanne * 0.08
    ticks, schritt = _schoene_schritte(lo, hi)
    lo, hi = ticks[0], ticks[-1]

    def x(d):
        return L + (d.toordinal() - x0) / (x1 - x0) * (B - L - R)

    def y(v):
        return O + (1 - (float(v) - lo) / (hi - lo)) * (hoehe - O - U)

    teile = [_y_achse(ticks, y, _stellen(schritt), einheit)]
    teile.append(_x_achse(date.fromordinal(x0), date.fromordinal(x1), x, hoehe))
    for s in serien:
        pts = [p for p in s["punkte"] if p[1] is not None]
        if not pts:
            continue
        pfad = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v, _ in pts)
        farbe = escape(s.get("farbe", "var(--blau)"))
        if flaeche:
            teile.append(f'<polygon points="{x(pts[0][0]):.1f},{y(lo):.1f} {pfad} {x(pts[-1][0]):.1f},{y(lo):.1f}" '
                         f'fill="{farbe}" opacity="0.12"/>')
        strich = ' stroke-dasharray="5 4"' if s.get("gestrichelt") else ""
        teile.append(f'<polyline points="{pfad}" fill="none" stroke="{farbe}" stroke-width="2"{strich} '
                     f'stroke-linejoin="round"/>')
        if len(pts) <= 120:
            radius = 2 if len(pts) <= 40 else 1.5   # dichte Reihen: kleinere Punkte, Linie bleibt sichtbar
            for d, v, titel in pts:
                text = titel or f'{s["name"]}: {deutsch(v, stellen_wert)} {einheit} ({d:%d.%m.%y})'
                teile.append(f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="{radius}" fill="{farbe}">'
                             f'<title>{escape(text)}</title></circle>')
    return _rahmen(hoehe, "".join(teile), ", ".join(s["name"] for s in serien))


def _x_achse(von, bis, x, hoehe):
    tage = (bis - von).days
    teile = []
    marken = []
    if tage > 500:
        for j in range(von.year + 1, bis.year + 1):
            marken.append((date(j, 1, 1), str(j)))
    else:
        d = date(von.year, von.month, 1)
        schritt = 1 if tage < 200 else 2 if tage < 400 else 3
        while d <= bis:
            if d >= von:
                marken.append((d, MONATE[d.month - 1] + (f" {d:%y}" if d.month == 1 else "")))
            m = d.month - 1 + schritt
            d = date(d.year + m // 12, m % 12 + 1, 1)
    for d, text in marken:
        xx = x(d)
        teile.append(f'<line class="gitter" x1="{xx:.1f}" x2="{xx:.1f}" y1="{O}" y2="{hoehe - U}"/>')
        teile.append(f'<text class="achse" x="{xx:.1f}" y="{hoehe - 8}" text-anchor="middle">{text}</text>')
    return "".join(teile)


def balken(beschriftungen, stapel, einheit="€", stellen_wert=0, hoehe=H):
    """Gestapelte Balken. stapel: [{"name", "farbe", "werte": [Zahl je Beschriftung]}]"""
    if not beschriftungen or not stapel:
        return leer()
    summen = [sum(float(s["werte"][i] or 0) for s in stapel) for i in range(len(beschriftungen))]
    if max(summen) <= 0:
        return leer()
    ticks, schritt = _schoene_schritte(0, max(summen))
    hi = ticks[-1]

    def y(v):
        return O + (1 - float(v) / hi) * (hoehe - O - U)

    teile = [_y_achse(ticks, y, _stellen(schritt), einheit)]
    breite = (B - L - R) / len(beschriftungen)
    bb = min(breite * 0.62, 56)
    for i, text in enumerate(beschriftungen):
        xx = L + breite * i + (breite - bb) / 2
        basis = 0.0
        for s in stapel:
            v = float(s["werte"][i] or 0)
            if v <= 0:
                continue
            titel = f'{text} – {s["name"]}: {deutsch(v, 2)} {einheit}'
            teile.append(f'<rect x="{xx:.1f}" y="{y(basis + v):.1f}" width="{bb:.1f}" '
                         f'height="{y(basis) - y(basis + v):.1f}" fill="{escape(s["farbe"])}">'
                         f'<title>{escape(titel)}</title></rect>')
            basis += v
        teile.append(f'<text class="achse" x="{xx + bb / 2:.1f}" y="{hoehe - 8}" text-anchor="middle">'
                     f'{escape(text)}</text>')
    return _rahmen(hoehe, "".join(teile), "Balkendiagramm")


def ring(teile_, gesamt_text=""):
    """Ringdiagramm. teile_: [(Name, Farbe, Wert)]"""
    teile_ = [(n, f, float(w)) for n, f, w in teile_ if w and float(w) > 0]
    summe = sum(w for _, _, w in teile_)
    if summe <= 0:
        return leer()
    cx, cy, r, dicke = 120, 120, 92, 34
    umfang = 2 * math.pi * r
    teile = []
    versatz = 0.0
    for name, farbe, w in teile_:
        laenge = w / summe * umfang
        titel = f"{name}: {deutsch(w, 2)} € ({deutsch(Decimal(w / summe * 100), 1)} %)"
        teile.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{escape(farbe)}" '
                     f'stroke-width="{dicke}" stroke-dasharray="{laenge:.2f} {umfang - laenge:.2f}" '
                     f'stroke-dashoffset="{-versatz:.2f}" transform="rotate(-90 {cx} {cy})">'
                     f'<title>{escape(titel)}</title></circle>')
        versatz += laenge
    if gesamt_text:
        teile.append(f'<text class="ring-text" x="{cx}" y="{cy + 6}" text-anchor="middle">{escape(gesamt_text)}</text>')
    return mark_safe(f'<svg class="ring" viewBox="0 0 240 240" role="img" aria-label="Kostenverteilung">'
                     f'{"".join(teile)}</svg>')

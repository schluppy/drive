"""Alle E-Mails der Anwendung an einer Stelle."""
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from konten.models import MagicLinkToken


def _link(pfad):
    return settings.BASIS_URL + pfad


def _senden(person, betreff, vorlage, kontext):
    kontext = {"person": person, "basis_url": settings.BASIS_URL, **kontext}
    text = render_to_string(f"portal/mail/{vorlage}.txt", kontext)
    send_mail(betreff, text, settings.DEFAULT_FROM_EMAIL, [person.email])


def anmeldelink(person, ip=None, ziel=""):
    token = MagicLinkToken.erzeugen(person, ip=ip, ziel=ziel)
    _senden(person, "Dein Anmeldelink – Drive", "anmeldelink", {
        "link": _link(reverse("portal:token", args=[token])),
        "minuten": settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN,
    })


def einladung(person, von, ip=None):
    from .views import einladung_gueltigkeit
    token = MagicLinkToken.erzeugen(person, ip=ip, gueltigkeit=einladung_gueltigkeit(), ziel=reverse("portal:start"))
    _senden(person, f"{von.vorname} lädt dich zu Drive ein", "einladung", {
        "von": von, "familie": person.familie,
        "link": _link(reverse("portal:token", args=[token])),
        "tage": settings.EINLADUNG_GUELTIGKEIT_TAGE,
    })


def erinnerungen(person, faellige):
    """faellige: [(Fahrzeug, Faelligkeit)]"""
    _senden(person, "Drive: " + ", ".join(f"{fl.erinnerung.kategorie} {f}" for f, fl in faellige[:3])
            + (" …" if len(faellige) > 3 else ""), "erinnerungen", {"faellige": faellige})

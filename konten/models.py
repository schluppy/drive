"""Familien (Mandanten), Personen und Magic-Link-Login.

Jede Person gehört zu einer Familie und sieht nur deren Fahrzeuge, Logbücher und
Auswertungen – dort aber alles, damit die Familie ihre Verbräuche vergleichen kann.
Mitglieder laden weitere Personen in die eigene Familie ein. Der Super-Admin
(is_superuser) legt neue Familien an; die Fahrzeuge anderer Familien sieht auch er nicht.
Keine Passwörter: Login über einmalig gültige Links per E-Mail.
"""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

# Farben der Personen in den Vergleichsdiagrammen (unterscheidbar, auch hell/dunkel)
PERSONENFARBEN = ["#1f6fb2", "#e07b16", "#2e8b57", "#b23a6f", "#6b4fbb", "#8a6d1f", "#0e8a8a", "#c0392b"]


class Familie(models.Model):
    name = models.CharField("Name", max_length=80, unique=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Familie"
        verbose_name_plural = "Familien"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PersonManager(BaseUserManager):
    def create_user(self, email, name="", **extra):
        if not email:
            raise ValueError("E-Mail-Adresse fehlt")
        person = self.model(email=self.normalize_email(email).lower(), name=name, **extra)
        person.set_unusable_password()
        person.save(using=self._db)
        return person

    def create_superuser(self, email, name="", password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        person = self.create_user(email, name, **extra)
        if password:
            person.set_password(password)
            person.save(using=self._db)
        return person


class Person(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("E-Mail", unique=True)
    name = models.CharField("Name", max_length=150)
    is_active = models.BooleanField("aktiv", default=True)
    is_staff = models.BooleanField("Zugang Verwaltung", default=False)
    familie = models.ForeignKey(Familie, verbose_name="Familie", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="personen")
    farbe = models.CharField("Farbe im Vergleich", max_length=7, blank=True,
                             help_text="leer = automatisch")
    erinnerungen_per_mail = models.BooleanField("Erinnerungen per E-Mail", default=True)
    angelegt_am = models.DateTimeField(auto_now_add=True)
    zuletzt_aktiv = models.DateTimeField("zuletzt aktiv", null=True, blank=True, editable=False,
                                         help_text="letzter Seitenaufruf mit Anmeldung, auf wenige Minuten genau")

    objects = PersonManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["name"]

    def __str__(self):
        return self.name or self.email

    @property
    def vorname(self):
        return (self.name or self.email).split()[0]

    @property
    def diagrammfarbe(self):
        if self.farbe:
            return self.farbe
        return PERSONENFARBEN[(self.pk or 0) % len(PERSONENFARBEN)]


class MagicLinkToken(models.Model):
    """Einmal-Token für den Login. Gespeichert wird nur der Hash."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="login_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    gueltig_bis = models.DateTimeField()
    verwendet_am = models.DateTimeField(null=True, blank=True)
    angefordert_von_ip = models.GenericIPAddressField(null=True, blank=True)
    ziel = models.CharField(max_length=200, blank=True, help_text="Seite nach dem Login")

    class Meta:
        verbose_name = "Login-Token"
        verbose_name_plural = "Login-Tokens"

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def erzeugen(cls, person, ip=None, gueltigkeit=None, ziel=""):
        """Gibt den Klartext-Token zurück; er steht nur im Link der E-Mail."""
        token = secrets.token_urlsafe(32)
        gueltigkeit = gueltigkeit or timedelta(minutes=settings.MAGIC_LINK_GUELTIGKEIT_MINUTEN)
        cls.objects.create(
            person=person,
            token_hash=cls._hash(token),
            gueltig_bis=timezone.now() + gueltigkeit,
            angefordert_von_ip=ip,
            ziel=ziel,
        )
        return token

    @classmethod
    def finde_gueltig(cls, token):
        return cls.objects.select_related("person").filter(
            token_hash=cls._hash(token), verwendet_am__isnull=True, gueltig_bis__gte=timezone.now()
        ).first()

    @classmethod
    def zu_viele_anfragen(cls, person=None, ip=None):
        """Begrenzung: 5 Links pro Person und 20 pro IP-Adresse je Stunde."""
        seit = timezone.now() - timedelta(hours=1)
        if person and cls.objects.filter(person=person, erstellt_am__gte=seit).count() >= 5:
            return True
        if ip and cls.objects.filter(angefordert_von_ip=ip, erstellt_am__gte=seit).count() >= 20:
            return True
        return False

    @classmethod
    def einloesen(cls, token):
        """Liefert die Person bei gültigem Token, sonst None. Ein Token
        funktioniert genau einmal."""
        jetzt = timezone.now()
        eintrag = (
            cls.objects.select_related("person")
            .filter(token_hash=cls._hash(token), verwendet_am__isnull=True, gueltig_bis__gte=jetzt)
            .first()
        )
        if eintrag is None or not eintrag.person.is_active:
            return None
        # Bedingtes Update schützt gegen doppeltes Einlösen bei parallelen Klicks.
        aktualisiert = cls.objects.filter(pk=eintrag.pk, verwendet_am__isnull=True).update(
            verwendet_am=jetzt
        )
        return eintrag.person if aktualisiert else None

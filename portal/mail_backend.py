"""E-Mail-Versand über msmtp.

Die Zugangsdaten zum Mailserver liegen nur in der msmtp-Konfiguration
(/etc/msmtprc im Container, vom Host eingebunden), nicht in Django.
Aktivieren mit EMAIL_BACKEND=portal.mail_backend.MsmtpBackend.
"""
import subprocess

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class MsmtpFehler(Exception):
    pass


class MsmtpBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        gesendet = 0
        for nachricht in email_messages:
            empfaenger = nachricht.recipients()
            if not empfaenger:
                continue
            befehl = [settings.MSMTP_BINARY, "-a", settings.MSMTP_ACCOUNT, "--", *empfaenger]
            try:
                ergebnis = subprocess.run(befehl, input=nachricht.message().as_bytes(),
                                          capture_output=True, timeout=60)
            except (OSError, subprocess.TimeoutExpired) as e:
                if not self.fail_silently:
                    raise MsmtpFehler(f"msmtp nicht ausführbar: {e}") from e
                continue
            if ergebnis.returncode != 0:
                if not self.fail_silently:
                    raise MsmtpFehler(ergebnis.stderr.decode(errors="replace").strip())
                continue
            gesendet += 1
        return gesendet

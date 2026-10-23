# Drive

Fahrtenbuch für Familien (Nachbau der Android-App DriveNote) mit Familienvergleich.
Django 5.2, Postgres 17, Login per Magic-Link, Mailversand über msmtp. Details in `README.md`.

## Apps

- `konten` – Familien (Mandanten), Personen, Magic-Link-Tokens
- `fahrzeuge` – Fahrzeuge, Kraftstoffe, Foto
- `logbuch` – Kategorien, Einträge, Serien, Erinnerungen; `verbrauch.py` = Fachlogik
- `auswertung` – Kennzahlen, Statistik, Kosten, Vergleich, SVG-Diagramme
- `importe` – DriveNote-Backup lesen und übernehmen
- `portal` – Anmeldung, Start, Familie, Mails (`mail_backend.py` = msmtp), Vorlagen, CSS; `zugriff.py` trennt die Familien

## Regeln

- Jede View holt Fahrzeuge/Einträge/Kategorien über `portal/zugriff.py` (fremde IDs → 404).
  Neue Seiten in `tests/test_familien.py` aufnehmen.
- Verbrauch immer über `logbuch/verbrauch.py` (voll bis voll); Werte sind gegen das eigene
  Backup geprüft (`tests/test_backup_privat.py`, privat).

## Betrieb

- Compose-Stack `drive-web-1` (gunicorn) und `drive-db-1` (Postgres), Web nur auf `127.0.0.1:8030`.
- Nginx auf dem Host terminiert TLS für `drive.schluppeck.de` (`betrieb/nginx-drive.schluppeck.de.conf`).
- Konfiguration in `.env`, Mailkonto in `msmtprc` + `msmtp.env` – nie committen.
- Deploy: `docker compose up -d --build`

## Tests

    docker run --rm -u 1000:1000 -v /opt/drive:/app drive-web python manage.py test tests

## Hinweise

- Kein sudo, kein lokales pip/venv – alles läuft im Container.
- Nginx, Cron, Backups und Zugangsdaten macht Stefan selbst.
- Editor: vim. Sprache in Code, Kommentaren und Antworten: Deutsch.

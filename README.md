# Drive

Selbst gehostetes Fahrtenbuch für Familien und Freunde – nachgebaut nach der Android-App
[DriveNote](https://play.google.com/store/apps/details?id=de.drivenote.android): Tankfüllungen,
Fahrten, Kosten, Serien und Erinnerungen je Fahrzeug, mit Statistik und Kostenauswertung.
Dazu, was DriveNote nicht kann: **Alle in der Familie sehen alle Fahrzeuge und vergleichen**,
wer am sparsamsten fährt und wer mit einer Tankfüllung am weitesten kommt.

Django 5.2, PostgreSQL, Docker Compose; Oberfläche mit Django-Templates ohne JS-Framework,
Diagramme als SVG vom Server. Fürs Handy gebaut, lässt sich als Web-App auf den Startbildschirm legen.

## Was die App kann

- **Fahrzeuge** mit Foto, Kennzeichen, Versicherung, Kauf und Verkauf; bis zu zwei Kraftstoffe
  (z. B. Diesel + AdBlue); Anhänger und Wohnwagen ohne Kraftstoff, mit Fahrten.
- **Logbuch** nach Monaten: Tankfüllung (Gesamtpreis, Preis pro Liter, Menge – zwei reichen),
  voll oder Teilfüllung, „vorherige Tankfüllung nicht erfasst“, Bordcomputer-Verbrauch;
  Fahrten mit Start und Ziel; Kosteneinträge in eigenen Kategorien; Prüfung, ob Tachostand und
  Datum zu den übrigen Einträgen passen.
- **Verbrauch** von voller zu voller Tankfüllung: Gesamt, Aktuell (mit Trendpfeil), Bordcomputer
  (nach Strecke gewichtet) – gerechnet wie DriveNote (`logbuch/verbrauch.py`).
- **Statistik**: Verbrauch, Strecke je Tankfüllung, Preis je Liter, Fahrleistung, Tachostand;
  je Jahr oder gesamt.
- **Kosten**: Verteilung nach Kategorie, Entwicklung je Jahr bzw. Monat, Kosten pro km (kumuliert).
- **Serien** für wiederkehrende Kosten (Versicherung, Steuer …), täglich gebucht.
- **Erinnerungen** nach Datum, Tachostand oder beidem, auch wiederkehrend (TÜV alle 24 Monate,
  Inspektion alle 30.000 km); fehlende Werte werden aus der Fahrleistung geschätzt; Mail vorher.
- **Familienvergleich**: Bestenliste (sparsamstes Fahrzeug, weiteste und sparsamste Tankfüllung,
  günstigster Sprit, meiste Kilometer), Rangliste der Fahrzeuge und der Personen, Verlauf.
  Jede Tankfüllung zählt für die Person, die sie eingetragen hat – auch bei geteilten Autos.
- **Import von DriveNote-Backups** (Format 15, App 1.11): Fahrzeuge, Fotos, Kategorien, Logbuch,
  Erinnerungen. Jede Person importiert ihr eigenes Backup; dasselbe Auto aus zwei Handys wird
  zusammengeführt, ein neueres Backup aktualisiert statt zu verdoppeln.
- **Mehrere Familien** (Mandanten); jede sieht nur ihre eigenen Daten. Mitglieder laden weitere
  Personen per Mail ein.
- **Anmeldung ohne Passwort** über einmalig gültige Links per E-Mail.

## Aufbau

| App          | Inhalt |
|--------------|--------|
| `konten`     | Familien, Personen, Anmeldelinks; Verwaltung nur für den Super-Admin |
| `fahrzeuge`  | Fahrzeuge mit Kraftstoffen, Kauf/Verkauf, Foto (nur für die eigene Familie ausgeliefert) |
| `logbuch`    | Kategorien, Einträge, Serien, Erinnerungen; Fachlogik in `verbrauch.py`; Befehle `erinnerungen`, `serien_buchen` |
| `auswertung` | Kennzahlen (`kennzahlen.py`), Statistik, Kosten, Familienvergleich, SVG-Diagramme (`diagramme.py`) |
| `importe`    | DriveNote-Backup lesen (`drivenote.py`, Felder dort beschrieben) und übernehmen (`uebernahme.py`) |
| `portal`     | Anmeldung, Start, Familie/Einladungen, Profil, Datenschutz, Mails, Vorlagen und CSS |

Trennung der Familien: Jede Seite holt Daten nur über `portal/zugriff.py`; fremde IDs ergeben 404.

## Rollen

| Rolle | Darf |
|---|---|
| **Mitglied** | alle Fahrzeuge der eigenen Familie bearbeiten, Backups importieren, Personen einladen |
| **Super-Admin** | zusätzlich unter `/verwaltung/` Familien und Personen anlegen – die Fahrzeuge anderer Familien sieht auch er nicht |

## Installation

Voraussetzungen: Docker mit Compose, ein Reverse Proxy für HTTPS (Vorlage für Nginx in
`betrieb/nginx-drive.schluppeck.de.conf`) und ein SMTP-Konto.

    git clone https://github.com/schluppy/drive.git && cd drive
    cp .env.example .env && chmod 600 .env          # Werte eintragen, s. Kommentare in der Datei
    cp betrieb/msmtprc.beispiel msmtprc && chmod 600 msmtprc
    printf 'MSMTP_PASSWORD=geheim\n' > msmtp.env && chmod 600 msmtp.env
    docker compose up -d --build
    docker compose exec web python manage.py person_anlegen du@example.org "Dein Name" --familie Muster --super-admin

Die Anwendung lauscht auf `127.0.0.1:8030`. Ohne Mailserver zum Ausprobieren: in `.env`
`EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` – der Anmeldelink steht dann
im Log (`docker compose logs web | grep anmelden/link`).

Nach Änderungen an `.env`: `docker compose up -d --force-recreate web`.
Nach Codeänderungen: `docker compose up -d --build`.

### Regelmäßige Aufgaben (Cron)

    15 6 * * *  cd /pfad/zu/drive && docker compose exec -T web python manage.py serien_buchen >> erinnerungen.log 2>&1
    0 7 * * *   cd /pfad/zu/drive && docker compose exec -T web python manage.py erinnerungen >> erinnerungen.log 2>&1
    45 3 * * *  /pfad/zu/drive/betrieb/backup.sh >> /var/log/drive-backup.log 2>&1

`backup.sh` sichert Datenbank, Fotos und Konfiguration nach `/var/backups/drive`
(höchstens `BACKUP_TAGE` Tage, optional Kopie nach `BACKUP_EXTERN`).

### Weitere Befehle

| Befehl | Zweck |
|---|---|
| `drivenote_import DATEI EMAIL [--trocken] [--zuordnung 4=neu 2=aus 1=17]` | Backup ohne Oberfläche importieren |
| `erinnerungen --trocken --heute 2027-11-20` | zeigt, was an einem Tag verschickt würde |
| `person_anlegen` | erste Person bzw. Super-Admin anlegen |

## DriveNote-Backup

Ein Backup ist ein ZIP mit `META`, `db.d` (ZIP mit gzip-XML-Tabellen `vh.s` Fahrzeuge, `cg.s`
Kategorien, `lb.s` Logbuch, `rm.s` Erinnerungen, `rl.s` Serien) und `pv.d` (Fotos). Die
Feldbedeutungen stehen in `importe/drivenote.py`. Geprüft an einem echten Backup: Gesamt-,
Aktuell- und BC-Verbrauch, Kosten pro km und Erinnerungen stimmen mit der App überein.
Einzige bekannte Abweichung: eine Teilfüllung mit Füllstand 0 % rechnet DriveNote anders.

## Tests

    docker build -t drive-web .
    docker run --rm -u 1000:1000 -v "$PWD":/app drive-web python manage.py test tests

`tests/test_familien.py` prüft die Trennung der Familien, `tests/test_verbrauch.py` die
Verbrauchsrechnung, `tests/test_import.py` den Import an einem künstlichen Backup.

## Lizenz

MIT (siehe `LICENSE`). Nicht verbunden mit DriveNote.

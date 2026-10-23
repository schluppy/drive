#!/bin/sh
# Tägliche Sicherung von Drive. Cron (crontab -e als root):
#   45 3 * * *  /opt/drive/betrieb/backup.sh >> /var/log/drive-backup.log 2>&1
#
# Sichert nach $ZIEL (Standard /var/backups/drive), höchstens $BACKUP_TAGE Tage (Standard 14):
#   db-JJJJ-MM-TT.dump       Datenbank (pg_dump, Custom-Format)
#   media-JJJJ-MM-TT.tgz     Fahrzeugfotos (Volume media)
#   konfig-JJJJ-MM-TT.tgz    .env, msmtprc, msmtp.env
# Optional zusätzlich: BACKUP_EXTERN=/pfad (in .env), z. B. ein eingebundenes Netzlaufwerk.
# Schlägt die Kopie nach außen fehl, bleibt die lokale Sicherung erhalten (Exit-Code 2).
set -eu
PROJEKT=$(cd "$(dirname "$0")/.." && pwd)
cd "$PROJEKT"

wert() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }
ZIEL=${ZIEL:-/var/backups/drive}
BACKUP_TAGE=${BACKUP_TAGE:-$(wert BACKUP_TAGE)}
BACKUP_TAGE=${BACKUP_TAGE:-14}
# -mtime +N löscht erst ab N+1 vollen Tagen; mit N = BACKUP_TAGE-1 bleiben höchstens BACKUP_TAGE Tagesstände
ALTER=$((BACKUP_TAGE - 1))
EXTERN=${BACKUP_EXTERN:-$(wert BACKUP_EXTERN)}
DB=$(wert POSTGRES_DB); DB=${DB:-drive}
DB_USER=$(wert POSTGRES_USER); DB_USER=${DB_USER:-drive}
STAMP=$(date +%F)

mkdir -p "$ZIEL"
chmod 700 "$ZIEL"

# 1. Datenbank – erst in eine Teildatei, damit ein Abbruch keine halbe Sicherung hinterlässt
docker compose exec -T db pg_dump -U "$DB_USER" -Fc "$DB" > "$ZIEL/db-$STAMP.dump.teil"
mv "$ZIEL/db-$STAMP.dump.teil" "$ZIEL/db-$STAMP.dump"

# 2. Fotos
docker compose run --rm --no-deps --user 0 -v "$ZIEL":/backup web \
  tar czf "/backup/media-$STAMP.tgz" -C /app media

# 3. Konfiguration (nur vorhandene Dateien)
LISTE=""
for f in .env msmtprc msmtp.env; do [ -e "$f" ] && LISTE="$LISTE $f"; done
# shellcheck disable=SC2086
tar czf "$ZIEL/konfig-$STAMP.tgz" $LISTE
chmod 600 "$ZIEL/db-$STAMP.dump" "$ZIEL/media-$STAMP.tgz" "$ZIEL/konfig-$STAMP.tgz"

find "$ZIEL" -maxdepth 1 -type f \( -name 'db-*' -o -name 'media-*' -o -name 'konfig-*' \) -mtime +"$ALTER" -delete
echo "$(date '+%F %T') lokal: $(ls -1 "$ZIEL" | wc -l) Dateien in $ZIEL, heute $(du -ch "$ZIEL"/*-"$STAMP".* | tail -1 | cut -f1)"

# 4. Optional: Kopie in ein weiteres Verzeichnis
if [ -n "$EXTERN" ]; then
    if mkdir -p "$EXTERN" && cp "$ZIEL/db-$STAMP.dump" "$ZIEL/media-$STAMP.tgz" "$ZIEL/konfig-$STAMP.tgz" "$EXTERN/"; then
        find "$EXTERN" -maxdepth 1 -type f \( -name 'db-*' -o -name 'media-*' -o -name 'konfig-*' \) -mtime +"$ALTER" -delete
        echo "$(date '+%F %T') extern: kopiert nach $EXTERN"
    else
        echo "$(date '+%F %T') FEHLER: Kopie nach $EXTERN fehlgeschlagen – lokale Sicherung ist vorhanden" >&2
        exit 2
    fi
fi

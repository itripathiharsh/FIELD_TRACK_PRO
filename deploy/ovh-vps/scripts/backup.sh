#!/usr/bin/env bash
# FieldTrack Pro - nightly backup: PostgreSQL (custom-format dump, restorable with pg_restore) + uploaded media.
#
# Reads /etc/fieldtrack/backend.env for the DB URL and media path (override with BACKUP_ENV_FILE for tests).
# Uses the OWNER connection so pg_dump can read every object. Keeps BACKUP_KEEP_DAYS (default 14) of history.
# Backups are 0600 in a 0700 directory. OFF-SERVER COPY IS NOT DONE HERE: a backup that lives only on the machine it protects is
# not a backup - see README "Off-server copy" and set BACKUP_RCLONE_REMOTE (optional) to push each run.
set -euo pipefail
umask 077

ENV_FILE="${BACKUP_ENV_FILE:-/etc/fieldtrack/backend.env}"
DEST="${BACKUP_DIR:-/var/backups/fieldtrack}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

[ -r "$ENV_FILE" ] || { echo "cannot read $ENV_FILE" >&2; exit 2; }
get() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

URL="$(get MIGRATION_DATABASE_URL)"; [ -n "$URL" ] || URL="$(get DATABASE_URL)"
MEDIA="$(get MEDIA_STORAGE_PATH)"
[ -n "$URL" ] || { echo "no database URL in $ENV_FILE" >&2; exit 2; }
# postgresql+asyncpg://user:pass@host:port/db  ->  libpq pieces (password goes via PGPASSWORD, never on the command line)
rest="${URL#*://}"; creds="${rest%%@*}"; hostdb="${rest#*@}"
export PGUSER="${creds%%:*}" PGPASSWORD="${creds#*:}"
[[ "$PGPASSWORD" =~ ^[A-Za-z0-9]+$ ]] || { echo "database password must be alphanumeric (openssl rand -hex 24)" >&2; exit 2; }
hostport="${hostdb%%/*}"; export PGDATABASE="${hostdb#*/}"
export PGHOST="${hostport%%:*}" PGPORT="${hostport#*:}"
[ "$PGPORT" = "$hostport" ] && PGPORT=5432 && export PGPORT

mkdir -p "$DEST"; chmod 700 "$DEST"
DB_OUT="$DEST/db-$STAMP.dump"
pg_dump --format=custom --no-owner --file="$DB_OUT.partial"
mv "$DB_OUT.partial" "$DB_OUT"
pg_restore --list "$DB_OUT" > /dev/null          # proves the archive is readable
echo "database dump ok: $DB_OUT ($(wc -c < "$DB_OUT") bytes)"

if [ -n "$MEDIA" ] && [ -d "$MEDIA" ]; then
  MEDIA_OUT="$DEST/media-$STAMP.tar.gz"
  tar -czf "$MEDIA_OUT.partial" -C "$(dirname "$MEDIA")" "$(basename "$MEDIA")"
  mv "$MEDIA_OUT.partial" "$MEDIA_OUT"
  echo "media archive ok: $MEDIA_OUT ($(wc -c < "$MEDIA_OUT") bytes)"
fi

# retention
find "$DEST" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) -mtime "+$KEEP_DAYS" -print -delete || true

# optional off-server copy
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  rclone copy "$DEST" "$BACKUP_RCLONE_REMOTE" --include 'db-*.dump' --include 'media-*.tar.gz' --max-age "2d"
  echo "off-server copy pushed to $BACKUP_RCLONE_REMOTE"
else
  echo "WARNING: BACKUP_RCLONE_REMOTE not set - backups exist only on this server" >&2
fi

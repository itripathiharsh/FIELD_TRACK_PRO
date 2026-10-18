#!/usr/bin/env bash
# FieldTrack Pro - schema migration of the production database, with a read-only pre-flight and the runtime grants.
#
#   sudo ./20_migrate.sh                 # pre-flight only (read-only): shows revision, pending migrations, what the demo-data purge would hit
#   sudo ./20_migrate.sh --apply         # pre-flight, then `alembic upgrade head`, then scripts/grant_runtime_role.sql, then re-check
#
# Run from any directory; it targets /opt/fieldtrack/current unless RELEASE_DIR is set (use that to migrate a release you have
# installed but NOT yet switched to). Stops at the first problem. NEVER bypasses the pre-flight: if it reports a problem (exit 1)
# - unknown revision, schema mismatch, or the demo-data purge matching rows - nothing is migrated.
set -euo pipefail

APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
RELEASE_DIR="${RELEASE_DIR:-/opt/fieldtrack/current}"
BACKEND="$RELEASE_DIR/fieldtrackpro-backend"
ENV_FILE="${ENV_FILE:-/etc/fieldtrack/backend.env}"
[ -x "$BACKEND/.venv/bin/python" ] || { echo "no virtualenv at $BACKEND/.venv (run 10_install_release.sh first)"; exit 2; }
[ -r "$ENV_FILE" ] || { echo "cannot read $ENV_FILE"; exit 2; }

# load KEY=VALUE lines WITHOUT shell interpretation (passwords may contain $ ! & etc.)
while IFS='=' read -r k v; do case "$k" in ''|\#*) continue;; esac; export "$k=$v"; done < "$ENV_FILE"
export ENVIRONMENT=production

# split the owner URL (postgresql+asyncpg://user:pass@host:port/db) for psql; the password must be URL-safe because we do not percent-decode
rest="${MIGRATION_DATABASE_URL#*://}"; creds="${rest%%@*}"; hostdb="${rest#*@}"
OWNER="${creds%%:*}"; export PGPASSWORD="${creds#*:}"
hostport="${hostdb%%/*}"; DB="${hostdb#*/}"; HOST="${hostport%%:*}"; PORT="${hostport#*:}"; [ "$PORT" = "$hostport" ] && PORT=5432
[[ "$PGPASSWORD" =~ ^[A-Za-z0-9]+$ ]] || { echo "database passwords must be alphanumeric (generate with: openssl rand -hex 24); characters like # @ / ? : break the URL"; exit 2; }
cd "$BACKEND"
PY=".venv/bin/python"

echo "== 1/4 pre-flight (read-only)"
CHECK_DATABASE_URL="${MIGRATION_DATABASE_URL:?MIGRATION_DATABASE_URL missing in $ENV_FILE}" "$PY" scripts/preflight_db_revision.py || {
  rc=$?; echo "PRE-FLIGHT REPORTED A PROBLEM (exit $rc). Nothing was changed. Resolve it before migrating."; exit "$rc"; }

if [ "$APPLY" -ne 1 ]; then echo; echo "Pre-flight clean. Re-run with --apply to migrate."; exit 0; fi

echo "== 2/4 alembic upgrade head (as the owner role)"
"$PY" -m alembic upgrade head

echo "== 3/4 runtime role grants (as the owner role)"
psql -h "$HOST" -p "$PORT" -U "$OWNER" -d "$DB" -v ON_ERROR_STOP=1 -v owner_role="$OWNER" -f scripts/grant_runtime_role.sql

echo "== 4/4 post-check"
CHECK_DATABASE_URL="$MIGRATION_DATABASE_URL" "$PY" scripts/preflight_db_revision.py | grep -E "Stored revision|Pending to head|RESULT"
echo "migration complete."

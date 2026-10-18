#!/usr/bin/env bash
# FieldTrack Pro - create the FIRST administrator and promote the FIRST Super Admin on a fresh production database.
#
#   sudo ./30_bootstrap_admins.sh            # interactive; passwords are read silently and never written to disk or printed
#
# 1. scripts/bootstrap_admin.py        creates ONE admin account (refuses if the email already exists; never resets a password).
# 2. scripts/bootstrap_super_admin.py  dry-runs, shows what it would do, asks for confirmation, then promotes that same account.
# Run once. A second run is refused by the scripts themselves.
set -euo pipefail

RELEASE_DIR="${RELEASE_DIR:-/opt/fieldtrack/current}"
BACKEND="$RELEASE_DIR/fieldtrackpro-backend"
ENV_FILE="${ENV_FILE:-/etc/fieldtrack/backend.env}"
[ -r "$ENV_FILE" ] && [ -x "$BACKEND/.venv/bin/python" ] || { echo "release/env not ready"; exit 2; }
while IFS='=' read -r k v; do case "$k" in ''|\#*) continue;; esac; export "$k=$v"; done < "$ENV_FILE"
export ENVIRONMENT=production
# the bootstrap scripts use the OWNER connection (the runtime role cannot insert users before grants, and must not be able to promote itself)
export DATABASE_URL="${MIGRATION_DATABASE_URL:?}"
cd "$BACKEND"; PY=".venv/bin/python"

read -r -p "Email of the first administrator: " EMAIL
[ -n "$EMAIL" ] && [[ "$EMAIL" == *@* ]] || { echo "need a valid email"; exit 2; }
read -r -s -p "Password (min 12 characters; not echoed): " PW; echo
read -r -s -p "Repeat password: " PW2; echo
[ "$PW" = "$PW2" ] || { echo "passwords differ"; exit 2; }
[ "${#PW}" -ge 12 ] || { echo "password too short"; exit 2; }

ADMIN_BOOTSTRAP_EMAIL="$EMAIL" ADMIN_BOOTSTRAP_PASSWORD="$PW" "$PY" scripts/bootstrap_admin.py --i-understand-production
unset PW PW2

export SUPER_ADMIN_BOOTSTRAP_IDENTIFIER="$EMAIL"
echo; echo "--- dry run of the Super Admin promotion"
"$PY" scripts/bootstrap_super_admin.py --confirm-identifier "$EMAIL" --i-understand-production
read -r -p "Promote $EMAIL to SUPER_ADMIN now? type YES: " ANS
[ "$ANS" = "YES" ] || { echo "not promoted. Re-run the script later."; exit 0; }
"$PY" scripts/bootstrap_super_admin.py --confirm-identifier "$EMAIL" --execute --i-understand-production
echo "done. Sign in on the admin web app with $EMAIL; the account is forced through a normal login (no temporary password involved)."

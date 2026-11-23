#!/usr/bin/env bash
# Release 3.1 production rollout - one controlled session. Stops at the first failed step or guard.
#   sudo bash rollout.sh
set -euo pipefail
REL=77cfca0
RDIR=/opt/fieldtrack/releases/$REL/fieldtrackpro-backend
RULES=/root/scope_rules_2026-11-22.json
EXPECT=1534,23,51
PRE=fieldtrack_scope_precheck          # NEW scratch DB; fieldtrack_scope_dryrun is left untouched
LOG=/var/backups/fieldtrack/rollout_3.1_$(date +%Y%m%d-%H%M%S)
mkdir -p "$LOG"; chmod 700 "$LOG"
exec > >(tee -a "$LOG/rollout.log") 2>&1
step() { echo; echo "######## $(date '+%F %T %Z')  $*"; }
die() { echo "STOP: $*"; echo "LOG=$LOG"; exit 1; }
[ -x "$RDIR/.venv/bin/python" ] || die "release $REL not installed"
PREV=$(readlink -f /opt/fieldtrack/current); echo "current before: $PREV"
load_env() { set -a; while IFS='=' read -r k v; do case "$k" in ''|\#*) continue;; esac; export "$k=$v"; done < /etc/fieldtrack/backend.env; set +a; }

step "1 backup"
BK=$(env BACKUP_KEEP_DAYS=36500 /opt/fieldtrack/current/deploy/ovh-vps/scripts/backup.sh | tee "$LOG/backup.txt" | sed -n 's/^database dump ok: \([^ ]*\).*/\1/p')
[ -s "$BK" ] || die "backup missing"
pg_restore --list "$BK" > /dev/null || die "backup unreadable"
sha256sum "$BK" | tee "$LOG/backup.sha256"
echo "backup: $BK ($(stat -c %s "$BK") bytes) - pg_restore --list OK"

step "2 pre-apply guard check on a restore of that backup ($PRE)"
sudo -u postgres psql -X -q -c "DROP DATABASE IF EXISTS $PRE" -c "CREATE DATABASE $PRE OWNER fieldtrack_owner"
sudo -u postgres psql -X -q -d $PRE -c "CREATE EXTENSION IF NOT EXISTS postgis"
sudo -u postgres pg_restore --no-owner --role=fieldtrack_owner -d $PRE < "$BK" 2> "$LOG/precheck_restore.txt" || true
NT_S=$(sudo -u postgres psql -X -At -d $PRE -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
NT_P=$(sudo -u postgres psql -X -At -d fieldtrackpro_prod -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[ "$NT_S" = "$NT_P" ] || die "pre-check copy incomplete ($NT_S vs $NT_P tables)"
echo "restore usable: $NT_S/$NT_P tables"
( load_env
  export DATABASE_URL="${DATABASE_URL%/*}/$PRE" MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL%/*}/$PRE"
  case "$DATABASE_URL$MIGRATION_DATABASE_URL" in *fieldtrackpro_prod*) echo "URL still prod"; exit 2;; esac
  cd "$RDIR"
  .venv/bin/python -m alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" || true
  sudo -u postgres psql -X -q -d $PRE -v ON_ERROR_STOP=1 -v owner_role=fieldtrack_owner -f scripts/grant_runtime_role.sql > /dev/null
  .venv/bin/python scripts/tally_business_scope.py plan "$RULES" --expect "$EXPECT" --csv "$LOG/precheck_plan.csv" --i-understand-production 2>&1 | grep -v "^\[20"
) > "$LOG/precheck.txt" 2>&1 || { cat "$LOG/precheck.txt"; die "pre-apply guard check failed"; }
grep -E "decisions|guard_|DRY-RUN complete" "$LOG/precheck.txt"
grep -q '"guard_distribution_rows_unchanged": true' "$LOG/precheck.txt" || die "guard: distribution rows"
grep -q '"guard_allocations_unchanged": true' "$LOG/precheck.txt" || die "guard: allocations"
grep -q '"guard_distribution_customer_flags_unchanged": true' "$LOG/precheck.txt" || die "guard: customer flags"
grep -q "decisions: {'DISTRIBUTION': 1534, 'EXCLUDED': 23, 'PENDING': 51}" "$LOG/precheck.txt" || die "guard: counts"
echo "PRE-APPLY GUARDS PASSED"

step "3 migrate production (additive)"
RELEASE_DIR=/opt/fieldtrack/releases/$REL /opt/fieldtrack/releases/$REL/deploy/ovh-vps/scripts/20_migrate.sh --apply 2>&1 \
  | grep -v -E "^\s+[a-z0-9]{12}  |WARNING:  no privileges" | tee "$LOG/migrate.txt" | tail -8
grep -q "Stored revision : s1c0p3d1st5r" "$LOG/migrate.txt" || die "migration did not reach s1c0p3d1st5r"

step "4 activate $REL"
ln -sfn /opt/fieldtrack/releases/$REL /opt/fieldtrack/current.new && mv -T /opt/fieldtrack/current.new /opt/fieldtrack/current
echo "current -> $(readlink -f /opt/fieldtrack/current) (previous $PREV)"
systemctl restart fieldtrack-backend
for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 2; done
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] || die "health check failed after activation (rollback: ln -sfn $PREV /opt/fieldtrack/current; systemctl restart fieldtrack-backend)"
echo "health 200, service $(systemctl is-active fieldtrack-backend)"

step "5 apply business-scope rules on production (one transaction, guarded)"
( load_env; cd "$RDIR"
  CONFIRM_PURGE_DATABASE=fieldtrackpro_prod .venv/bin/python scripts/tally_business_scope.py plan "$RULES" --expect "$EXPECT" \
      --csv "$LOG/applied_plan.csv" --execute --i-understand-production 2>&1 | grep -v "^\[20"
) > "$LOG/apply.txt" 2>&1 || { cat "$LOG/apply.txt"; die "apply refused / failed - nothing committed"; }
cat "$LOG/apply.txt"
grep -q "^COMMITTED." "$LOG/apply.txt" || die "apply not committed"

step "6 restart backend"
systemctl restart fieldtrack-backend
for i in $(seq 1 30); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)" = 200 ] && break; sleep 2; done
echo "health $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health), service $(systemctl is-active fieldtrack-backend) since $(systemctl show fieldtrack-backend -p ActiveEnterTimestamp --value)"
echo "ROLLOUT APPLIED. LOG=$LOG"

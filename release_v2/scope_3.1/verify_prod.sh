#!/usr/bin/env bash
# Read-only post-rollout verification on production.  sudo bash verify_prod.sh <since 'YYYY-MM-DD HH:MM:SS'>
set -euo pipefail
SINCE="$1"
set -a; while IFS='=' read -r k v; do case "$k" in ''|\#*) continue;; esac; export "$k=$v"; done < /etc/fieldtrack/backend.env; set +a
cd /opt/fieldtrack/current/fieldtrackpro-backend
echo "current -> $(readlink -f /opt/fieldtrack/current); service $(systemctl is-active fieldtrack-backend) since $(systemctl show fieldtrack-backend -p ActiveEnterTimestamp --value); health $(curl -s https://51-79-158-138.sslip.io/health)"
SINCE="$SINCE" .venv/bin/python - <<'PY'
import asyncio, json, os
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services import tally_reconciliation
from datetime import datetime, timedelta, timezone
SINCE = datetime.fromisoformat(os.environ["SINCE"]).replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
async def go():
    async with AsyncSessionLocal() as s:
        await s.execute(text("SET TRANSACTION READ ONLY"))
        q = lambda sql, **p: s.execute(text(sql), p)
        rep = await tally_reconciliation.build_report(s, limit=5)
        print("== reconciliation")
        print(json.dumps({k: rep[k] for k in ("totals", "counts", "debtors_reconciled", "debtors_with_difference",
                                               "excluded_business_scope")}, indent=1, default=str))
        print("== visibility")
        print("scope rules:", (await q("SELECT count(*) FROM tally_scope_groups")).scalar(),
              "| ledgers by scope:", dict((await q("SELECT business_scope, count(*) FROM tally_debtor_ledgers WHERE is_debtor GROUP BY 1")).all()))
        print("visible debtor outlets (outlet-list clause):", (await q(
            "SELECT count(*) FROM customers WHERE tally_is_debtor IS TRUE AND merged_into_customer_id IS NULL")).scalar())
        print("out-of-scope ledgers on a visible outlet:", (await q("""SELECT string_agg(l.name, '; ') FROM tally_debtor_ledgers l
              JOIN customers c ON c.id=l.customer_id WHERE l.business_scope IN ('EXCLUDED','PENDING') AND c.tally_is_debtor""")).scalar())
        print("live invoices / receipts / adjustments on out-of-scope ledgers:", (await q("""SELECT
              (SELECT count(*) FROM invoices i JOIN tally_debtor_ledgers l ON l.id=i.tally_debtor_ledger_id WHERE l.business_scope IN ('EXCLUDED','PENDING') AND i.source='TALLY'),
              (SELECT count(*) FROM payments p JOIN tally_debtor_ledgers l ON l.id=p.tally_debtor_ledger_id WHERE l.business_scope IN ('EXCLUDED','PENDING') AND p.source='TALLY'),
              (SELECT count(*) FROM tally_ledger_adjustments a JOIN tally_debtor_ledgers l ON l.id=a.tally_debtor_ledger_id WHERE l.business_scope IN ('EXCLUDED','PENDING') AND a.state='ACTIVE')""")).one())
        print("named non-Distribution entities still visible:", [r[0] for r in (await q("""SELECT name FROM customers WHERE tally_is_debtor IS NOT FALSE
              AND merged_into_customer_id IS NULL AND name ~* '(sgrg infra|sgrg automobiles|zepto|office driver|scheme payout|sgrg services)'""")).all()])
        print("Distribution totals: live invoices", (await q("SELECT count(*), sum(amount) FROM invoices WHERE source='TALLY'")).one(),
              "| receipts", (await q("SELECT count(*), sum(amount) FROM payments WHERE source='TALLY'")).one(),
              "| allocations", (await q("SELECT count(*) FROM payment_invoice_allocations")).scalar())
        print("== agent")
        a = (await q("""SELECT agent_version, tally_status, last_heartbeat_at, last_sync_at, health->>'last_cycle_status',
                        health->>'last_cycle_completed_at', health->'retry_queue'->>'pending', health->'quarantine'->>'unresolved'
                        FROM sync_agents WHERE id='79820679-d959-4086-91d3-679818a87edf'""")).one()
        print(dict(zip(["version", "tally_status", "last_heartbeat", "last_sync", "last_cycle", "cycle_completed_utc", "retry", "quarantine"], [str(x) for x in a])))
        print("audit since", SINCE, ":", [tuple(map(str, r)) for r in (await q("""SELECT operation, status, count(*), sum(record_count), max(created_at)
              FROM tally_audit_logs WHERE created_at >= :t GROUP BY 1,2 ORDER BY 1""", t=SINCE)).all()])
        print("ledger rows with scope changes since:", (await q("SELECT count(*) FROM tally_debtor_ledgers WHERE scope_decided_at >= :t AND scope_decided_at > (SELECT max(started_at) FROM tally_snapshot_runs WHERE started_at < :t)", t=SINCE)).scalar())
        await s.rollback()
asyncio.run(go())
PY
echo "== backend tally calls since $SINCE"
journalctl -u fieldtrack-backend --since "$SINCE" --no-pager -o cat | grep -o "path=/api/v1/integrations/tally/[^ ]* status=[0-9]*" | sort | uniq -c
echo "errors since: $(journalctl -u fieldtrack-backend --since "$SINCE" --no-pager -o cat | grep -c -i -E 'traceback|\[ERROR\]|status=5[0-9][0-9]')"

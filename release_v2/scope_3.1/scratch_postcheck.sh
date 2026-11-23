#!/usr/bin/env bash
# Post-apply measurements on the THROWAWAY copy fieldtrack_scope_dryrun (after the scratch-only commit).
#   sudo bash scratch_postcheck.sh <OUT dir>
set -euo pipefail
OUT="$1"; SCRATCH=fieldtrack_scope_dryrun
RDIR=/opt/fieldtrack/releases/77cfca0/fieldtrackpro-backend
echo "== restore messages (should be extension 'already exists' only)"; cut -c1-160 "$OUT/restore_warnings.txt"
set -a; while IFS='=' read -r k v; do case "$k" in ''|\#*) continue;; esac; export "$k=$v"; done < /etc/fieldtrack/backend.env; set +a
export DATABASE_URL="${DATABASE_URL%/*}/$SCRATCH" MIGRATION_DATABASE_URL="${MIGRATION_DATABASE_URL%/*}/$SCRATCH"
case "$DATABASE_URL" in *fieldtrackpro_prod*) echo refusing; exit 2;; esac
cd "$RDIR"
.venv/bin/python - <<'PY'
import asyncio, json
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services import tally_reconciliation
async def go():
    async with AsyncSessionLocal() as s:
        rep = await tally_reconciliation.build_report(s, limit=10)
        print("== reconciliation (scratch, after apply)")
        print(json.dumps({k: rep[k] for k in ("totals", "counts", "debtors_reconciled", "debtors_with_difference",
                                               "unallocated_total", "excluded_business_scope")}, indent=1, default=str))
        q = lambda sql: s.execute(text(sql))
        r = (await q("""SELECT count(*) FILTER (WHERE c.tally_is_debtor) visible
                        FROM tally_debtor_ledgers l JOIN customers c ON c.id=l.customer_id
                        WHERE l.business_scope IN ('EXCLUDED','PENDING')""")).scalar()
        print("excluded/pending ledgers whose outlet is still a visible debtor:", r)
        r = (await q("""SELECT count(*) FROM invoices i JOIN tally_debtor_ledgers l ON l.id=i.tally_debtor_ledger_id
                        WHERE l.business_scope IN ('EXCLUDED','PENDING') AND i.source='TALLY'""")).scalar()
        print("live invoices left on excluded/pending ledgers:", r)
        r = (await q("""SELECT count(*) FROM payments p JOIN tally_debtor_ledgers l ON l.id=p.tally_debtor_ledger_id
                        WHERE l.business_scope IN ('EXCLUDED','PENDING') AND p.source='TALLY'""")).scalar()
        print("live receipts left on excluded/pending ledgers:", r)
        r = (await q("SELECT count(*) FROM tally_voucher_index WHERE state='ACTIVE'")).scalar()
        print("voucher index ACTIVE rows (unchanged by scope):", r)
        names = [x[0] for x in (await q("""SELECT c.name FROM customers c WHERE c.tally_is_debtor IS NOT FALSE
                   AND c.merged_into_customer_id IS NULL AND c.name ~* '(sgrg infra|sgrg automobiles|zepto|office driver)'""")).all()]
        print("outlet-list query (tally_is_debtor IS NOT FALSE) still showing named non-Distribution entities:", names)
asyncio.run(go())
PY
sudo -u postgres psql -X -q -d $SCRATCH -c "\copy (SELECT l.business_scope AS scope, l.scope_source, l.name AS tally_ledger, l.parent_group, x.kind, x.number, x.dt, x.vtype, x.amount, x.reason FROM tally_debtor_ledgers l JOIN (SELECT tally_debtor_ledger_id lid, 'invoice' kind, invoice_number number, invoice_date dt, tally_voucher_type vtype, amount, tally_retired_reason reason FROM invoices WHERE tally_retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING') UNION ALL SELECT tally_debtor_ledger_id, 'receipt', right(coalesce(tally_voucher_guid,''),8), payment_date::date, tally_voucher_type, amount, tally_retired_reason FROM payments WHERE tally_retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING') UNION ALL SELECT tally_debtor_ledger_id, 'adjustment', voucher_number, voucher_date, voucher_type, amount, retired_reason FROM tally_ledger_adjustments WHERE retired_reason IN ('OUT_OF_SCOPE','SCOPE_PENDING')) x ON x.lid = l.id ORDER BY 1, 3, 7) TO '$OUT/records_to_retire.csv' CSV HEADER"
wc -l "$OUT/records_to_retire.csv"
cp "$OUT/scope_plan.csv" "$OUT/records_to_retire.csv" /tmp/ && chmod 644 /tmp/scope_plan.csv /tmp/records_to_retire.csv

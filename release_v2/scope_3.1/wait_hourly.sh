#!/usr/bin/env bash
# Wait (read-only) for the first hourly run after the 3.1 activation, then report it.  sudo bash wait_hourly.sh
SINCE="2026-11-22 19:40:38"
for i in $(seq 1 45); do
  if journalctl -u fieldtrack-backend --since "$SINCE" --no-pager -o cat | grep -q "path=/api/v1/integrations/tally/sync/reconcile"; then
    sleep 30; break
  fi
  sleep 20
done
echo "server now $(date +%T)"
echo "== tally sync calls since $SINCE (time, path, status)"
journalctl -u fieldtrack-backend --since "$SINCE" --no-pager -o short-iso | grep "event=http_request" | grep "/integrations/tally/sync/" \
  | sed -E 's/^([^ ]+) .*path=([^ ]+) status=([0-9]+) duration_ms=([0-9.]+).*/\1 \2 \3 \4ms/' | cut -c12-19,26-
echo "== errors since: $(journalctl -u fieldtrack-backend --since "$SINCE" --no-pager -o cat | grep -c -i -E 'traceback|\[ERROR\]|status=5[0-9][0-9]')"
cat > /tmp/wh.sql <<'SQL'
\pset footer off
BEGIN TRANSACTION READ ONLY;
SELECT kind, status, received_count, started_at::timestamp(0), completed_at::timestamp(0), left(details::text, 160) details
  FROM tally_snapshot_runs WHERE started_at >= '2026-11-22 19:40:38+05:30' ORDER BY started_at;
SELECT operation, status, count(*), sum(record_count), max(created_at)::timestamp(0) FROM tally_audit_logs
 WHERE created_at >= '2026-11-22 19:40:38+05:30' GROUP BY 1,2 ORDER BY 1;
SELECT business_scope, count(*) FROM tally_debtor_ledgers WHERE is_debtor GROUP BY 1 ORDER BY 1;
SELECT count(*) AS ledgers_scope_changed_after_rollout FROM tally_debtor_ledgers WHERE scope_decided_at > '2026-11-22 19:40:40+05:30';
SELECT count(*) AS live_on_out_of_scope FROM invoices i JOIN tally_debtor_ledgers l ON l.id=i.tally_debtor_ledger_id
 WHERE l.business_scope IN ('EXCLUDED','PENDING') AND i.source::text='TALLY';
SELECT (SELECT count(*) FROM invoices WHERE source::text='TALLY') inv, (SELECT count(*) FROM payments WHERE source::text='TALLY') rct,
       (SELECT count(*) FROM tally_ledger_adjustments WHERE state='ACTIVE') adj, (SELECT max(updated_at)::timestamp(0) FROM tally_voucher_index) index_last_update,
       (SELECT count(*) FROM tally_voucher_index WHERE updated_at > '2026-11-22 19:40:38+05:30') index_rows_after_rollout;
SELECT agent_version, tally_status, last_heartbeat_at::timestamp(0) hb, last_sync_at::timestamp(0) last_sync,
       health->>'last_cycle_status' cyc, health->>'last_cycle_completed_at' cyc_utc, health->'retry_queue'->>'pending' retry,
       health->'retry_queue'->>'rejected_4xx' rejected, health->'quarantine'->>'unresolved' quarantine,
       last_checkpoints->'vouchers_v2'->>'last_alter_id' vouchers_alter_id,
       last_checkpoints->'reconcile_hourly_v3'->>'last_successful_sync_at' hourly_utc
  FROM sync_agents WHERE id='79820679-d959-4086-91d3-679818a87edf';
ROLLBACK;
SQL
sudo -u postgres psql -X -d fieldtrackpro_prod -f /tmp/wh.sql | grep -v -E "^(BEGIN|ROLLBACK)$"
rm -f /tmp/wh.sql

"""
FieldTrack Pro - Distribution-only business scope (release 3.1): load rules, dry-run, apply, decide, roll back.

    python scripts/tally_business_scope.py status
    python scripts/tally_business_scope.py plan  RULES.json [--csv OUT.csv] [--expect D,E,P] [--execute]
    python scripts/tally_business_scope.py set-ledger LEDGER_GUID {DISTRIBUTION|EXCLUDED|PENDING|AUTO} --reason "..." [--execute]
    python scripts/tally_business_scope.py disable [--execute]          # full rollback of the scope feature's data effect

RULES.json:
    {"groups":  {"<Tally group>": "DISTRIBUTION" | "EXCLUDED", ...},
     "ledgers": {"<ledger GUID>": {"scope": "DISTRIBUTION" | "EXCLUDED" | "PENDING", "reason": "..."}, ...}}

Safety model (as scripts/_script_env.destructive_script_main):
  * DEFAULT IS DRY-RUN: everything runs in ONE transaction that is ROLLED BACK; the printed counts and the CSV are
    exactly what would be applied.
  * --execute needs env CONFIRM_PURGE_DATABASE=<database name>; ENVIRONMENT=production also needs
    --i-understand-production.
  * `plan --expect D,E,P` refuses (rolls back) unless the decided debtor ledgers are exactly D distribution,
    E excluded and P pending.
  * Guards inside the transaction: the rows of every DISTRIBUTION ledger and every payment allocation must be
    byte-identical before and after (md5 fingerprints), or nothing is committed.
Nothing is deleted. Nothing is written to Tally.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.tally_debtor_ledger import (  # noqa: E402
    SCOPE_DISTRIBUTION, SCOPE_EXCLUDED, SCOPE_PENDING, SCOPE_SOURCE_MANUAL, TallyDebtorLedger)
from app.models.tally_scope_group import TallyScopeGroup  # noqa: E402
from app.services import business_scope as bs  # noqa: E402

# Rows of DISTRIBUTION ledgers (and rows on no ledger): must not change. Allocations: must not change at all.
_FP_ROWS = """
WITH dist AS (SELECT id FROM tally_debtor_ledgers WHERE NOT (id = ANY(:out)))
SELECT md5(coalesce((SELECT string_agg(to_jsonb(i)::text, '|' ORDER BY i.id) FROM invoices i
                      WHERE i.tally_debtor_ledger_id IS NULL OR i.tally_debtor_ledger_id IN (SELECT id FROM dist)), ''))
    || md5(coalesce((SELECT string_agg(to_jsonb(p)::text, '|' ORDER BY p.id) FROM payments p
                      WHERE p.tally_debtor_ledger_id IS NULL OR p.tally_debtor_ledger_id IN (SELECT id FROM dist)), ''))
    || md5(coalesce((SELECT string_agg(to_jsonb(a)::text, '|' ORDER BY a.id) FROM tally_ledger_adjustments a
                      WHERE a.tally_debtor_ledger_id IS NULL OR a.tally_debtor_ledger_id IN (SELECT id FROM dist)), ''))
"""
_FP_ALLOC = "SELECT md5(coalesce(string_agg(to_jsonb(a)::text, '|' ORDER BY a.id), '')) FROM payment_invoice_allocations a"
_FP_DIST_CUSTOMERS = """
SELECT md5(coalesce(string_agg(c.id::text || ':' || coalesce(c.tally_is_debtor::text,'null'), '|' ORDER BY c.id), ''))
  FROM customers c WHERE NOT EXISTS (SELECT 1 FROM tally_debtor_ledgers l WHERE l.customer_id = c.id AND l.id = ANY(:out))
"""


def _gate(args) -> str:
    db = urlparse(settings.database_url.replace("+asyncpg", "")).path.lstrip("/")
    if settings.environment == "production" and not args.i_understand_production:
        raise SystemExit("REFUSING: ENVIRONMENT=production requires --i-understand-production.")
    if args.execute and os.environ.get("CONFIRM_PURGE_DATABASE") != db:
        raise SystemExit(f"REFUSING: --execute requires env CONFIRM_PURGE_DATABASE={db!r}.")
    print("=" * 72)
    print(f"TALLY BUSINESS SCOPE {args.cmd.upper()} - database={db} - "
          f"{'EXECUTE (will COMMIT)' if args.execute else 'DRY-RUN (will ROLL BACK)'}")
    print("=" * 72)
    return db


async def _counts(s) -> dict:
    rows = (await s.execute(text("""
        SELECT coalesce(business_scope,'(null)') s, count(*) FROM tally_debtor_ledgers WHERE is_debtor IS TRUE GROUP BY 1
    """))).all()
    live = (await s.execute(text("""
        SELECT (SELECT count(*) FROM invoices WHERE source='TALLY'), (SELECT count(*) FROM payments WHERE source='TALLY'),
               (SELECT count(*) FROM tally_ledger_adjustments WHERE state='ACTIVE'),
               (SELECT count(*) FROM customers WHERE tally_is_debtor IS TRUE AND merged_into_customer_id IS NULL)
    """))).one()
    return {"ledgers_by_scope": dict(rows), "live_invoices": live[0], "live_payments": live[1],
            "live_adjustments": live[2], "debtor_customers": live[3]}


async def cmd_status(args) -> int:
    async with AsyncSessionLocal() as s:
        n = (await s.execute(select(TallyScopeGroup))).scalars().all()
        print(f"group rules: {len(n)} (enforcement {'ON' if n else 'OFF'})")
        print(json.dumps(await _counts(s), indent=1, default=str))
        print(json.dumps(await bs.excluded_summary(s), indent=1))
    return 0


async def cmd_plan(args) -> int:
    _gate(args)
    rules_doc = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    groups = rules_doc.get("groups", {})
    ledgers = rules_doc.get("ledgers", {})
    for g, sc in groups.items():
        if sc not in (SCOPE_DISTRIBUTION, SCOPE_EXCLUDED):
            raise SystemExit(f"group {g!r}: scope must be DISTRIBUTION or EXCLUDED")
    async with AsyncSessionLocal() as s:
        async with s.begin():
            before = await _counts(s)
            await s.execute(delete(TallyScopeGroup))
            for g, sc in groups.items():
                s.add(TallyScopeGroup(group_name=g[:150], scope=sc, reason=f"rules file {Path(args.rules).name}"))
            await s.flush()
            bs.forget_rules(s)
            rules = await bs.load_rules(s, refresh=True)
            debtors = (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.is_debtor.is_(True))
                                       .order_by(TallyDebtorLedger.name))).scalars().all()
            by_guid = {l.tally_guid: l for l in debtors}
            unknown = [g for g in ledgers if g not in by_guid]
            if unknown:
                raise SystemExit(f"REFUSING: {len(unknown)} ledger GUID(s) in the rules file are not debtor ledgers: {unknown[:5]}")
            # decisions first (no row touched yet)
            decided = {}
            for led in debtors:
                manual = ledgers.get(led.tally_guid)
                if manual:
                    if manual["scope"] not in bs.SCOPES:
                        raise SystemExit(f"ledger {led.tally_guid}: bad scope {manual['scope']!r}")
                    decided[led.id] = (manual["scope"], SCOPE_SOURCE_MANUAL, manual.get("reason") or "manual decision")
                else:
                    led.scope_source = None if led.scope_source == SCOPE_SOURCE_MANUAL else led.scope_source
                    decided[led.id] = bs.decide(led, rules)
            out_ids = [lid for lid, d in decided.items() if d[0] != SCOPE_DISTRIBUTION]
            tally = {sc: sum(1 for d in decided.values() if d[0] == sc) for sc in bs.SCOPES}
            print("decisions:", tally)
            if args.expect:
                exp = dict(zip(bs.SCOPES, (int(x) for x in args.expect.split(","))))
                if exp != tally:
                    raise SystemExit(f"REFUSING: expected {exp}, decided {tally}. Nothing applied.")
            fp_rows0 = (await s.execute(text(_FP_ROWS), {"out": out_ids})).scalar()
            fp_alloc0 = (await s.execute(text(_FP_ALLOC))).scalar()
            fp_cust0 = (await s.execute(text(_FP_DIST_CUSTOMERS), {"out": out_ids})).scalar()
            report = []
            now = bs._now()
            for led in debtors:
                scope, source, reason = decided[led.id]
                prev = led.business_scope
                r = await bs.transition(s, led, scope, source, reason, now)
                report.append({"decision": scope, "source": source, "reason": reason, "tally_ledger": led.name,
                               "parent_group": led.parent_group, "tally_guid": led.tally_guid,
                               "customer_id": str(led.customer_id), "previous_scope": prev,
                               "invoices_moved": r["invoices"], "payments_moved": r["payments"],
                               "adjustments_moved": r["adjustments"], "ledger_receivable": str(-(led.closing_balance or 0))})
            fp_rows1 = (await s.execute(text(_FP_ROWS), {"out": out_ids})).scalar()
            fp_alloc1 = (await s.execute(text(_FP_ALLOC))).scalar()
            fp_cust1 = (await s.execute(text(_FP_DIST_CUSTOMERS), {"out": out_ids})).scalar()
            after = await _counts(s)
            moved = {k: sum(r[f"{k}_moved"] for r in report if r["decision"] != SCOPE_DISTRIBUTION)
                     for k in ("invoices", "payments", "adjustments")}
            restored = {k: sum(r[f"{k}_moved"] for r in report if r["decision"] == SCOPE_DISTRIBUTION)
                        for k in ("invoices", "payments", "adjustments")}
            summary = {"before": before, "after": after, "retired_now": moved, "restored_now": restored,
                       "guard_distribution_rows_unchanged": fp_rows0 == fp_rows1,
                       "guard_allocations_unchanged": fp_alloc0 == fp_alloc1,
                       "guard_distribution_customer_flags_unchanged": fp_cust0 == fp_cust1,
                       "excluded_business_scope": await bs.excluded_summary(s)}
            print(json.dumps(summary, indent=1, default=str))
            if args.csv:
                with open(args.csv, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
                    w.writeheader()
                    w.writerows(sorted(report, key=lambda r: (r["decision"], r["tally_ledger"])))
                print(f"per-ledger report: {args.csv} ({len(report)} ledgers)")
            if not (summary["guard_distribution_rows_unchanged"] and summary["guard_allocations_unchanged"]):
                raise SystemExit("REFUSING: a Distribution row or an allocation would change. Rolled back.")
            if not args.execute:
                await s.rollback()
                print("DRY-RUN complete: everything rolled back, nothing was changed.")
                return 0
        print("COMMITTED.")
    return 0


async def cmd_set_ledger(args) -> int:
    _gate(args)
    async with AsyncSessionLocal() as s:
        async with s.begin():
            led = (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.tally_guid == args.guid))).scalar_one_or_none()
            if led is None:
                raise SystemExit("no such ledger")
            scope = None if args.scope == "AUTO" else args.scope
            r = await bs.set_manual_scope(s, led, scope, args.reason)
            print(json.dumps({"ledger": led.name, **r}, indent=1, default=str))
            if not args.execute:
                await s.rollback()
                print("DRY-RUN: rolled back.")
                return 0
        print("COMMITTED.")
    return 0


async def cmd_disable(args) -> int:
    """Rollback: every ledger back in scope, every scope-retired row restored, rules removed."""
    _gate(args)
    async with AsyncSessionLocal() as s:
        async with s.begin():
            before = await _counts(s)
            led_rows = (await s.execute(select(TallyDebtorLedger).where(TallyDebtorLedger.business_scope.is_not(None)))).scalars().all()
            restored = {"invoices": 0, "payments": 0, "adjustments": 0}
            for led in led_rows:
                r = await bs._restore_scope_retired(s, led.id)
                for k in restored:
                    restored[k] += r[k]
                led.business_scope = led.scope_source = led.scope_reason = None
                led.scope_decided_at = led.scope_decided_by = None
            await s.execute(delete(TallyScopeGroup))
            await s.flush()
            for cid in {l.customer_id for l in led_rows}:
                c = await s.get(Customer, cid)
                if c is not None:
                    await bs.refresh_customer_flag(s, c)
            print(json.dumps({"before": before, "restored": restored, "after": await _counts(s)}, indent=1, default=str))
            if not args.execute:
                await s.rollback()
                print("DRY-RUN: rolled back.")
                return 0
        print("COMMITTED.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    pl = sub.add_parser("plan")
    pl.add_argument("rules")
    pl.add_argument("--csv")
    pl.add_argument("--expect", help="D,E,P: exact number of DISTRIBUTION, EXCLUDED, PENDING debtor ledgers")
    sl = sub.add_parser("set-ledger")
    sl.add_argument("guid")
    sl.add_argument("scope", choices=[SCOPE_DISTRIBUTION, SCOPE_EXCLUDED, SCOPE_PENDING, "AUTO"])
    sl.add_argument("--reason", required=True)
    sub.add_parser("disable")
    for sp in (pl, sl, sub.choices["disable"]):
        sp.add_argument("--execute", action="store_true")
        sp.add_argument("--i-understand-production", action="store_true")
    args = p.parse_args(argv)
    fn = {"status": cmd_status, "plan": cmd_plan, "set-ledger": cmd_set_ledger, "disable": cmd_disable}[args.cmd]
    return asyncio.run(fn(args))


if __name__ == "__main__":
    sys.exit(main())

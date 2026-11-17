"""
FieldTrack vs Tally reconciliation (read-only).

Per debtor (receivable sign: positive = the customer owes):

    opening (Tally, at tally_opening_balance_as_of)
  + invoices  (TALLY, dated on/after that date)
  + adjustments (ACTIVE, signed)
  - receipts  (TALLY, dated on/after that date)
  - closing (Tally ledger balance at tally_closing_balance_at)
  = difference   -> must be 0.00; anything else is listed, never hidden.

Also reported: open bills vs closing (the unallocated part), retired rows by
reason, field collections linked to a retired receipt, non-debtor customers.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

ZERO = Decimal("0.00")

# Release 2.1.0: per Tally LEDGER (an outlet may hold several), rolled up per physical outlet.
# A row belongs to a ledger by tally_debtor_ledger_id; a row without one (pre-2.1.0) to the
# outlet's primary ledger. A legacy debtor customer without ledger rows is its own ledger.
_LEDGER_MATCH = ("(x.tally_debtor_ledger_id = l.lid OR (x.tally_debtor_ledger_id IS NULL AND l.is_primary "
                 "AND x.customer_id = l.cid))")
_PER_DEBTOR = text(f"""
WITH l AS (
  SELECT d.id AS lid, d.customer_id AS cid, d.name, d.tally_outlet_code AS outlet_code,
         d.opening_balance_as_of AS since, -COALESCE(d.opening_balance, 0) AS opening,
         -COALESCE(d.closing_balance, 0) AS closing, d.closing_balance_at AS closing_at, d.is_primary
    FROM tally_debtor_ledgers d WHERE d.is_debtor IS TRUE
  UNION ALL
  SELECT NULL, c.id, c.name, c.outlet_code, c.tally_opening_balance_as_of,
         -COALESCE(c.tally_opening_balance, 0), -COALESCE(c.tally_closing_balance, 0), c.tally_closing_balance_at, TRUE
    FROM customers c
   WHERE c.tally_is_debtor IS TRUE AND c.merged_into_customer_id IS NULL
     AND NOT EXISTS (SELECT 1 FROM tally_debtor_ledgers z WHERE z.customer_id = c.id)
     -- a merged customer's ledger now lives on its outlet; its stale balance fields are history only
),
inv AS (SELECT l.lid, l.cid, SUM(x.amount) s, COUNT(*) n FROM invoices x JOIN l ON {_LEDGER_MATCH}
         WHERE x.source = 'TALLY' AND (l.since IS NULL OR x.invoice_date >= l.since) GROUP BY 1, 2),
pay AS (SELECT l.lid, l.cid, SUM(x.amount) s, COUNT(*) n FROM payments x JOIN l ON {_LEDGER_MATCH}
         WHERE x.source = 'TALLY' AND (l.since IS NULL OR x.payment_date >= l.since) GROUP BY 1, 2),
adj AS (SELECT l.lid, l.cid, SUM(x.amount) s, COUNT(*) n FROM tally_ledger_adjustments x JOIN l ON {_LEDGER_MATCH}
         WHERE x.state = 'ACTIVE' AND (l.since IS NULL OR x.voucher_date >= l.since) GROUP BY 1, 2),
lb AS (SELECT MAX(as_of_date) d FROM tally_open_bills),
bills AS (SELECT l.lid, l.cid, SUM(x.pending_amount) s, COUNT(*) n FROM tally_open_bills x JOIN l ON {_LEDGER_MATCH}, lb
           WHERE x.as_of_date = lb.d GROUP BY 1, 2)
SELECT l.cid AS id, l.lid AS ledger_id, l.name, l.outlet_code, l.since, l.closing_at,
       l.opening, COALESCE(inv.s,0) invoiced, COALESCE(inv.n,0) invoice_count,
       COALESCE(adj.s,0) adjustments, COALESCE(adj.n,0) adjustment_count,
       COALESCE(pay.s,0) received, COALESCE(pay.n,0) receipt_count,
       l.closing, COALESCE(bills.s,0) open_bills, COALESCE(bills.n,0) open_bill_count,
       o.name AS outlet_name
  FROM l JOIN customers o ON o.id = l.cid
         LEFT JOIN inv ON inv.cid = l.cid AND inv.lid IS NOT DISTINCT FROM l.lid
         LEFT JOIN pay ON pay.cid = l.cid AND pay.lid IS NOT DISTINCT FROM l.lid
         LEFT JOIN adj ON adj.cid = l.cid AND adj.lid IS NOT DISTINCT FROM l.lid
         LEFT JOIN bills ON bills.cid = l.cid AND bills.lid IS NOT DISTINCT FROM l.lid
""")


async def build_report(session: AsyncSession, limit: int = 200) -> dict:
    rows = (await session.execute(_PER_DEBTOR)).mappings().all()
    totals = {k: ZERO for k in ("opening", "invoiced", "adjustments", "received", "closing", "open_bills")}
    counts = {"debtors": 0, "invoices": 0, "receipts": 0, "adjustments": 0, "open_bills": 0}
    differences = []
    outlet_diff: dict = {}
    for r in rows:
        diff = (r["opening"] + r["invoiced"] + r["adjustments"] - r["received"] - r["closing"]).quantize(Decimal("0.01"))
        for k in totals:
            totals[k] += r[k]
        counts["debtors"] += 1
        counts["invoices"] += r["invoice_count"]
        counts["receipts"] += r["receipt_count"]
        counts["adjustments"] += r["adjustment_count"]
        counts["open_bills"] += r["open_bill_count"]
        outlet_diff[r["id"]] = outlet_diff.get(r["id"], ZERO) + diff
        if diff != ZERO:
            differences.append({
                "customer_id": str(r["id"]), "ledger_id": str(r["ledger_id"]) if r["ledger_id"] else None,
                "outlet_name": r["outlet_name"], "name": r["name"], "outlet_code": r["outlet_code"],
                "opening": str(r["opening"]), "invoiced": str(r["invoiced"]), "adjustments": str(r["adjustments"]),
                "received": str(r["received"]), "closing": str(r["closing"]), "difference": str(diff),
                "closing_at": r["closing_at"].isoformat() if r["closing_at"] else None,
            })
    differences.sort(key=lambda d: abs(Decimal(d["difference"])), reverse=True)
    total_diff = totals["opening"] + totals["invoiced"] + totals["adjustments"] - totals["received"] - totals["closing"]

    retired = (await session.execute(text("""
        SELECT 'invoice' kind, tally_retired_reason reason, COUNT(*) n, COALESCE(SUM(amount),0) amt
          FROM invoices WHERE source = 'TALLY_RETIRED' GROUP BY 2
        UNION ALL
        SELECT 'receipt', tally_retired_reason, COUNT(*), COALESCE(SUM(amount),0)
          FROM payments WHERE source = 'TALLY_RETIRED' GROUP BY 2
        UNION ALL
        SELECT 'adjustment', retired_reason, COUNT(*), COALESCE(SUM(amount),0)
          FROM tally_ledger_adjustments WHERE state = 'RETIRED' GROUP BY 2
    """))).mappings().all()
    linked_to_retired = (await session.execute(text("""
        SELECT COUNT(*) FROM payments m JOIN payments r ON r.id = m.tally_receipt_payment_id
         WHERE m.source = 'MANUAL' AND r.source <> 'TALLY'
    """))).scalar() or 0
    non_debtors = (await session.execute(text(
        "SELECT COUNT(*) FROM customers WHERE tally_is_debtor IS FALSE"))).scalar() or 0
    runs = (await session.execute(text("""
        SELECT DISTINCT ON (kind) kind, id, as_of_date, window_from, window_to, status, received_count, completed_at
          FROM tally_snapshot_runs ORDER BY kind, started_at DESC
    """))).mappings().all()

    return {
        "totals": {k: str(v) for k, v in totals.items()} | {"difference": str(total_diff)},
        "counts": counts,
        "debtors_reconciled": counts["debtors"] - len(differences),
        "outlets": len(outlet_diff),
        "outlets_with_difference": sum(1 for v in outlet_diff.values() if v != ZERO),
        "debtors_with_difference": len(differences),
        "differences": differences[:limit],
        "unallocated_total": str(totals["closing"] - totals["open_bills"]),
        "retired": [{"kind": r["kind"], "reason": r["reason"], "count": r["n"], "amount": str(r["amt"])} for r in retired],
        "field_collections_linked_to_retired_receipt": linked_to_retired,
        "non_debtor_customers": non_debtors,
        "latest_snapshots": [
            {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r in runs
        ],
    }

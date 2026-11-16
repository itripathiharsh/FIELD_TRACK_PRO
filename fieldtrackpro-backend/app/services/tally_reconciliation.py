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

_PER_DEBTOR = text("""
WITH c AS (
  SELECT id, name, outlet_code, tally_opening_balance_as_of AS since,
         -COALESCE(tally_opening_balance, 0) AS opening,
         -COALESCE(tally_closing_balance, 0) AS closing,
         tally_closing_balance_at AS closing_at
    FROM customers WHERE tally_is_debtor IS TRUE
),
inv AS (SELECT i.customer_id, SUM(i.amount) s, COUNT(*) n FROM invoices i JOIN c ON c.id = i.customer_id
         WHERE i.source = 'TALLY' AND (c.since IS NULL OR i.invoice_date >= c.since) GROUP BY 1),
pay AS (SELECT p.customer_id, SUM(p.amount) s, COUNT(*) n FROM payments p JOIN c ON c.id = p.customer_id
         WHERE p.source = 'TALLY' AND (c.since IS NULL OR p.payment_date >= c.since) GROUP BY 1),
adj AS (SELECT a.customer_id, SUM(a.amount) s, COUNT(*) n FROM tally_ledger_adjustments a JOIN c ON c.id = a.customer_id
         WHERE a.state = 'ACTIVE' AND (c.since IS NULL OR a.voucher_date >= c.since) GROUP BY 1),
lb AS (SELECT MAX(as_of_date) d FROM tally_open_bills),
bills AS (SELECT b.customer_id, SUM(b.pending_amount) s, COUNT(*) n FROM tally_open_bills b, lb
           WHERE b.as_of_date = lb.d GROUP BY 1)
SELECT c.id, c.name, c.outlet_code, c.since, c.closing_at,
       c.opening, COALESCE(inv.s,0) invoiced, COALESCE(inv.n,0) invoice_count,
       COALESCE(adj.s,0) adjustments, COALESCE(adj.n,0) adjustment_count,
       COALESCE(pay.s,0) received, COALESCE(pay.n,0) receipt_count,
       c.closing, COALESCE(bills.s,0) open_bills, COALESCE(bills.n,0) open_bill_count
  FROM c LEFT JOIN inv ON inv.customer_id = c.id LEFT JOIN pay ON pay.customer_id = c.id
         LEFT JOIN adj ON adj.customer_id = c.id LEFT JOIN bills ON bills.customer_id = c.id
""")


async def build_report(session: AsyncSession, limit: int = 200) -> dict:
    rows = (await session.execute(_PER_DEBTOR)).mappings().all()
    totals = {k: ZERO for k in ("opening", "invoiced", "adjustments", "received", "closing", "open_bills")}
    counts = {"debtors": 0, "invoices": 0, "receipts": 0, "adjustments": 0, "open_bills": 0}
    differences = []
    for r in rows:
        diff = (r["opening"] + r["invoiced"] + r["adjustments"] - r["received"] - r["closing"]).quantize(Decimal("0.01"))
        for k in totals:
            totals[k] += r[k]
        counts["debtors"] += 1
        counts["invoices"] += r["invoice_count"]
        counts["receipts"] += r["receipt_count"]
        counts["adjustments"] += r["adjustment_count"]
        counts["open_bills"] += r["open_bill_count"]
        if diff != ZERO:
            differences.append({
                "customer_id": str(r["id"]), "name": r["name"], "outlet_code": r["outlet_code"],
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

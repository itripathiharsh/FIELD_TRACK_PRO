"""FieldTrack = Tally oracle, run after EVERY harness cycle.

Tally side  : the replay Tally's vouchers visible now, read from their XML by THIS module (it never uses the agent's
              parser), restricted to what FieldTrack must hold: dated in the live FY up to today, or in a historical
              FY whose upload is enabled.
FieldTrack  : the harness backend's PostgreSQL tables, read-only.

Checks
  guids      every Tally voucher is in tally_voucher_index ACTIVE; nothing else is ACTIVE there
  alter_ids  the index AlterID equals Tally's
  rows       per voucher and debtor ledger: kind (INVOICE / PAYMENT / ADJUSTMENT / none), ledger, signed amount,
             date and AlterID of the active FieldTrack row equal what Tally's lines give (the backend's documented
             classification: cancelled / optional / non-accounting -> no row; Sales + owed -> INVOICE; Receipt + paid
             -> PAYMENT; anything else -> ADJUSTMENT; one row per debtor ledger, key GUID or GUID::ledger)
  duplicates no key is active twice (across invoices, payments, adjustments)
  links      receipt -> invoice allocations (amount per invoice) equal Tally's bill allocations resolved the way
             the backend documents (bill name within the ledger; latest invoice on/before the receipt)
  outstanding per debtor ledger: FieldTrack opening + live-FY movements = Tally's closing today
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from replay_tally import NON_ACCOUNTING, ReplayTally, money

CENT = Decimal("0.01")
Q = lambda d: d.quantize(CENT)


class Expected:
    def __init__(self):
        self.index: Dict[str, Tuple[int, str]] = {}        # guid -> (alter, date)
        self.rows: Dict[str, tuple] = {}                    # key -> (kind, ledger lower, amount, date, alter, guid)
        self.links: Dict[Tuple[str, str], Decimal] = {}     # (payment key, invoice key) -> amount
        self.closing: Dict[str, Decimal] = {}               # ledger lower -> receivable (positive = owes)
        self.opening: Dict[str, Decimal] = {}               # ledger lower -> receivable at the live FY start


_parse_cache: Dict[str, tuple] = {}


def _voucher(tally: ReplayTally, r) -> tuple:
    """(cancelled, optional, parent, [(ledger name, amount, [(bill name, bill type, amount)])], debtor names)"""
    key = f"{r.guid}:{r.alter}:{len(tally.debtors)}"
    hit = _parse_cache.get(key)
    if hit:
        return hit
    e = ET.fromstring(r.xml)
    lines = []
    for le in e.findall("ALLLEDGERENTRIES.LIST"):
        n = (le.findtext("LEDGERNAME") or "").strip()
        if n.lower() not in tally.debtors:
            continue
        bills = [((b.findtext("NAME") or "").strip(), (b.findtext("BILLTYPE") or "").strip(), money(b.findtext("AMOUNT")))
                 for b in le.findall("BILLALLOCATIONS.LIST") if (b.findtext("AMOUNT") or "").strip()]
        lines.append((n, money(le.findtext("AMOUNT")), bills))
    out = ((e.findtext("ISCANCELLED") or "").strip().lower() == "yes",
           (e.findtext("ISOPTIONAL") or "").strip().lower() == "yes",
           tally.parent_of(r).strip().lower(), lines)
    _parse_cache[key] = out
    return out


def expected(tally: ReplayTally, today: date, live_start: date, history: List[Tuple[date, date]]) -> Expected:
    ex = Expected()
    windows = [(live_start, today)] + history
    invoices_by_bill: Dict[Tuple[str, str], List[tuple]] = defaultdict(list)   # (ledger, bill) -> [(date, key)]
    receipts = []
    for r in tally.visible():
        if not any(a <= r.date <= b for a, b in windows):
            continue
        ex.index[r.guid] = (r.alter, r.date.isoformat())
        cancelled, optional, parent, lines = _voucher(tally, r)
        if cancelled or optional or parent in NON_ACCOUNTING:
            continue
        agg: Dict[str, list] = {}
        order: List[str] = []
        for name, amt, bills in lines:
            k = name.lower()
            if k not in agg:
                agg[k] = [name, Decimal("0"), []]
                order.append(k)
            agg[k][1] += -amt
            agg[k][2].extend(bills)
        multi = len(order) > 1
        for k in order:
            name, rec, bills = agg[k]
            rec = Q(rec)
            if rec == 0:
                continue
            key = f"{r.guid}::{name}" if multi else r.guid
            if parent == "sales" and rec > 0:
                kind, amount = "INVOICE", rec
                named = [b for b in bills if b[0]]
                new_ref = [b for b in named if b[1].lower() == "new ref"]
                raised = new_ref[0][0] if new_ref else (named[0][0] if len(named) == 1 else None)
                if raised:
                    invoices_by_bill[(k, raised[:150])].append((r.date, key))
            elif parent == "receipt" and rec < 0:
                kind, amount = "PAYMENT", -rec
                receipts.append((key, k, r.date, amount, bills))
            else:
                kind, amount = "ADJUSTMENT", rec
            ex.rows[key] = (kind, k, amount, r.date.isoformat(), r.alter, r.guid)
    # receipt -> invoice links, resolved as the backend documents it
    for key, led, on, amount, bills in receipts:
        total = sum((Q(b[2]) for b in bills), Decimal("0"))
        if total - amount > CENT:
            continue
        per_name: Dict[str, Decimal] = {}
        for name, btype, amt in bills:
            if not name or btype.lower() == "on account":
                continue
            per_name[name] = per_name.get(name, Decimal("0")) + Q(amt)
        resolved: Dict[str, Decimal] = {}
        for name, amt in per_name.items():
            if amt == 0:
                continue
            cands = sorted(invoices_by_bill.get((led, name[:150]), []))
            if not cands:
                continue
            before = [c for c in cands if c[0] <= on]
            inv = (before[-1] if before else cands[0])[1]
            resolved[inv] = resolved.get(inv, Decimal("0")) + amt
        for inv, amt in resolved.items():
            if amt != 0:
                ex.links[(key, inv)] = amt
    # outstanding (live FY, today)
    for n, (opening, closing) in tally.debtor_balances(live_start, today).items():
        ex.closing[n] = Q(-closing)
        ex.opening[n] = Q(-opening)
    return ex


async def fieldtrack(conn) -> dict:
    ft = {}
    ft["index"] = {r["guid"]: (int(r["alter_id"]), r["voucher_date"].isoformat())
                   for r in await conn.fetch("SELECT guid, alter_id, voucher_date FROM tally_voucher_index WHERE state='ACTIVE'")}
    rows: Dict[str, list] = defaultdict(list)
    for r in await conn.fetch("""SELECT i.source_reference k, i.tally_alter_id a, i.invoice_date d, i.amount m, l.name n
                                 FROM invoices i LEFT JOIN tally_debtor_ledgers l ON l.id = i.tally_debtor_ledger_id
                                 WHERE i.source = 'TALLY'"""):
        rows[r["k"]].append(("INVOICE", (r["n"] or "").lower(), Q(r["m"]), r["d"].isoformat(), int(r["a"] or 0)))
    for r in await conn.fetch("""SELECT p.source_reference k, p.tally_alter_id a, p.payment_date d, p.amount m, l.name n
                                 FROM payments p LEFT JOIN tally_debtor_ledgers l ON l.id = p.tally_debtor_ledger_id
                                 WHERE p.source = 'TALLY'"""):
        rows[r["k"]].append(("PAYMENT", (r["n"] or "").lower(), Q(r["m"]), r["d"].isoformat(), int(r["a"] or 0)))
    for r in await conn.fetch("""SELECT a.source_reference k, a.tally_alter_id al, a.voucher_date d, a.amount m, l.name n
                                 FROM tally_ledger_adjustments a LEFT JOIN tally_debtor_ledgers l ON l.id = a.tally_debtor_ledger_id
                                 WHERE a.state = 'ACTIVE'"""):
        rows[r["k"]].append(("ADJUSTMENT", (r["n"] or "").lower(), Q(r["m"]), r["d"].isoformat(), int(r["al"] or 0)))
    ft["rows"] = rows
    ft["links"] = {}
    ft["links_to_retired"] = 0
    for r in await conn.fetch("""SELECT p.source_reference pk, i.source_reference ik, x.allocated_amount m,
                                        p.source ps, i.source isrc
                                 FROM payment_invoice_allocations x JOIN payments p ON p.id = x.payment_id
                                 JOIN invoices i ON i.id = x.invoice_id
                                 WHERE p.source IN ('TALLY', 'TALLY_RETIRED')"""):
        if r["ps"] == "TALLY" and r["isrc"] == "TALLY":
            ft["links"][(r["pk"], r["ik"])] = ft["links"].get((r["pk"], r["ik"]), Decimal("0")) + Q(r["m"])
        elif r["ps"] == "TALLY":
            ft["links_to_retired"] += 1
    ft["ledgers"] = {r["name"].lower(): (Q(-(r["opening_balance"] or Decimal("0"))), r["opening_balance_as_of"])
                     for r in await conn.fetch("SELECT name, opening_balance, opening_balance_as_of FROM tally_debtor_ledgers "
                                               "WHERE is_debtor IS TRUE")}
    return ft


def compare(ex: Expected, ft: dict, live_start: date) -> dict:
    out: Dict[str, list] = {k: [] for k in ("missing", "extra", "alter", "rows_missing", "rows_extra", "rows_wrong",
                                            "duplicates", "links_missing", "links_extra", "links_wrong", "outstanding")}
    idx = ft["index"]
    for g, (a, d) in ex.index.items():
        if g not in idx:
            out["missing"].append(g)
        elif idx[g][0] != a:
            out["alter"].append((g, idx[g][0], a))
    out["extra"] = [g for g in idx if g not in ex.index]
    rows = ft["rows"]
    for k, (kind, led, amt, d, a, g) in ex.rows.items():
        got = rows.get(k)
        if not got:
            out["rows_missing"].append(k)
            continue
        if len(got) > 1:
            out["duplicates"].append((k, len(got)))
        gk, gl, gm, gd, ga = got[0]
        if (gk, gl, gm, gd, ga) != (kind, led, amt, d, a):
            out["rows_wrong"].append((k, {"tally": (kind, led, str(amt), d, a), "fieldtrack": (gk, gl, str(gm), gd, ga)}))
    for k, got in rows.items():
        if k not in ex.rows:
            out["rows_extra"].append((k, got[0][0], str(got[0][2])))
        elif len(got) > 1 and (k, len(got)) not in out["duplicates"]:
            out["duplicates"].append((k, len(got)))
    for lk, amt in ex.links.items():
        if lk not in ft["links"]:
            out["links_missing"].append((lk, str(amt)))
        elif ft["links"][lk] != amt:
            out["links_wrong"].append((lk, str(amt), str(ft["links"][lk])))
    out["links_extra"] = [(lk, str(a)) for lk, a in ft["links"].items() if lk not in ex.links]
    # outstanding per debtor ledger: FieldTrack opening + live-FY movements
    mv: Dict[str, Decimal] = defaultdict(Decimal)
    for k, got in rows.items():
        kind, led, amt, d, _ = got[0]
        if d < live_start.isoformat():
            continue
        mv[led] += amt if kind in ("INVOICE", "ADJUSTMENT") else -amt
    for led, tally_rec in ex.closing.items():
        op = ft["ledgers"].get(led)
        ft_open = op[0] if op and op[1] == live_start else Decimal("0")
        ft_rec = ft_open + mv.get(led, Decimal("0"))
        if op is None and tally_rec == 0 and mv.get(led, Decimal("0")) == 0:
            continue
        if abs(ft_rec - tally_rec) > CENT:
            # which part differs: the opening (from the last ledger snapshot) or the synced movements
            open_bad = abs(ft_open - ex.opening.get(led, Decimal("0"))) > CENT
            mv_bad = abs(mv.get(led, Decimal("0")) - (tally_rec - ex.opening.get(led, Decimal("0")))) > CENT
            why = ("no ledger in FieldTrack" if op is None else
                   "+".join(x for x, b in (("opening", open_bad), ("movements", mv_bad)) if b))
            out["outstanding"].append((led, str(tally_rec), str(ft_rec), why))
    summary = {k: len(v) for k, v in out.items()}
    summary["tally_vouchers"] = len(ex.index)
    summary["tally_rows"] = len(ex.rows)
    summary["tally_links"] = len(ex.links)
    summary["fieldtrack_index_active"] = len(idx)
    summary["links_to_retired_invoices"] = ft["links_to_retired"]
    summary["equal"] = all(not v for v in out.values())
    return {"summary": summary, "samples": {k: v[:5] for k, v in out.items() if v}, "detail": out}

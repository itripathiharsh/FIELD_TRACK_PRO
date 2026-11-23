"""
Agent 2.2.1 - READ-ONLY validation of financial years against the client's Tally (AC3 / AC4).

    FieldTrackTallyAgent.exe validate-fy                         (all FINANCIAL_YEARS, full detail)
    FieldTrackTallyAgent.exe validate-fy --fy 2025-26 [--headers-only] [--resume <folder>]

Reads Tally only. Uploads NOTHING, writes no checkpoint, does not touch the agent's state. Only one
validate-fy may run on the machine (exclusive lock); every request goes through the TallyGuard (circuit
breaker, machine-wide request lock shared with 2.2.1 agents, duty-cycle pacing, telemetry), and TallyPrime's
"Responding" state is sampled every second for the whole run.

Per FY (window = FY start .. min(today, FY end)):
  * debtors and creditors read to the WINDOW END: count, sum opening, sum closing; Group Summary for the
    SAME dates (window end; previous FY end) must be equal (A5, items 17/18)
  * continuity: opening(FY) = closing(previous FY) per ledger (debtors and creditors) (item 21)
  * voucher headers, one MONTH-scoped request per month (B6): count, by type, cancelled, optional,
    no-GUID, duplicates, dated outside the FY
  * full detail (unless --headers-only), one DAY-scoped lean request per day, resumable (B7): parsed by the
    agent's own parser, same GUID set as the headers, every bill / bank allocation kept, and per LEDGER
    opening + movements (posting vouchers) = closing for every debtor AND creditor (item 19)
  * Bills Receivable / Payable as of the window end, typed form; any bill dated after the as-of date
    = FAIL (items 13-16); per-ledger bills vs closing breakdown (item 22)
  * live FY: the month-scoped incremental returns exactly what an FY-wide incremental returns (B4)
  * cross-FY: no GUID in two FYs (item 20)
"""
from __future__ import annotations

import csv
import json
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tally_sync_agent.config.fiscal import FinancialYear, ist_today
from tally_sync_agent.config.settings import AGENT_VERSION, settings
from tally_sync_agent.core.tally_client import TallyClient, TallyConnectionError
from tally_sync_agent.core.tally_guard import TallyGuard
from tally_sync_agent.core.tally_responsiveness import ResponsivenessSampler
from tally_sync_agent.engine.sync_engine_v2 import (TOLERANCE, BillsDateInvalid, TallyV2Source, _days, books_from_of,
                                                     check_bill_dates, month_chunks, posts_to_ledgers)
from tally_sync_agent.extractors import tally_xml as tx
from tally_sync_agent.extractors import v2_extractors as X

PASS, FAIL, INFO, NOT_VERIFIED = "PASS", "FAIL", "INFO", "NOT VERIFIED"


def _check(checks: List[Dict[str, Any]], name: str, ok: Optional[bool], detail: Any, status: Optional[str] = None) -> None:
    checks.append({"check": name, "status": status or (INFO if ok is None else (PASS if ok else FAIL)), "detail": detail})


def _header_rows(root: ET.Element) -> List[Dict[str, Any]]:
    rows = []
    for v in X.voucher_elements(root):
        rows.append({"guid": tx.text(v, "GUID"), "date": tx.ymd(tx.text(v, "DATE")) or "",
                     "type": tx.text(v, "VOUCHERTYPENAME") or v.attrib.get("VCHTYPE", ""),
                     "cancelled": tx.yes(v, "ISCANCELLED"), "optional": tx.yes(v, "ISOPTIONAL"),
                     "alter_id": int(tx.text(v, "ALTERID")) if tx.text(v, "ALTERID").isdigit() else 0})
    return rows


def _continuity(cur: Dict[str, Dict[str, Any]], prev: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    equal, diff, ex = 0, 0, []
    for k, b in cur.items():
        p = prev.get(k)
        if p is None:
            continue
        if abs(p["closing"] - b["opening"]) <= TOLERANCE:
            equal += 1
        else:
            diff += 1
            if len(ex) < 10:
                ex.append({"ledger": b["name"], "previous_closing": str(p["closing"]), "opening": str(b["opening"])})
    return {"equal": equal, "different": diff, "examples": ex}


def ledger_movements(root: ET.Element, m: X.Masters, names: set) -> Dict[str, Decimal]:
    """Sum of every ledger line (by lower-case ledger name, restricted to `names`) of the POSTING vouchers in
    a voucher answer: not cancelled, not optional, an accounting voucher type."""
    out: Dict[str, Decimal] = {}
    for v in X.voucher_elements(root):
        vtype = tx.text(v, "VOUCHERTYPENAME") or v.attrib.get("VCHTYPE", "").strip()
        meta = {"is_cancelled": tx.yes(v, "ISCANCELLED"), "is_optional": tx.yes(v, "ISOPTIONAL"), "voucher_type": vtype,
                "voucher_parent": m.voucher_parent.get(vtype)}
        if not posts_to_ledgers(meta):
            continue
        for e in X._entries(v):
            n = tx.text(e, "LEDGERNAME").strip().lower()
            a = tx.amount(tx.text(e, "AMOUNT"))
            if n in names and a is not None:
                out[n] = out.get(n, Decimal("0")) + a
    return out


def _reconcile(bal: Dict[str, Dict[str, Any]], mv: Dict[str, Decimal]) -> List[Dict[str, Any]]:
    bad = []
    for k, b in bal.items():
        got = b["opening"] + mv.get(k, Decimal("0"))
        if abs(got - b["closing"]) > TOLERANCE:
            bad.append({"ledger": b["name"], "opening": str(b["opening"]), "movements": str(mv.get(k, Decimal("0"))),
                        "closing": str(b["closing"]), "difference": str(b["closing"] - got)})
    return bad


def bills_vs_balances(bills: List[Dict[str, Any]], bal: Dict[str, Dict[str, Any]], on_account: Dict[str, Decimal],
                      unallocated: Dict[str, Decimal]) -> Dict[str, Any]:
    """Item 22: per ledger, closing balance vs sum of its open bills. Reported, never suppressed."""
    per: Dict[str, Decimal] = {}
    for b in bills:
        k = b["ledger_name"].strip().lower()
        per[k] = per.get(k, Decimal("0")) + Decimal(str(b["pending_amount"]))
    rows, total = [], Decimal("0")
    for k, b in bal.items():
        d = per.get(k, Decimal("0")) - b["closing"]
        if abs(d) > TOLERANCE:
            total += d
            rows.append({"ledger": b["name"], "closing": str(b["closing"]), "bills_sum": str(per.get(k, Decimal("0"))),
                         "bills_minus_closing": str(d), "on_account_allocations_in_fy": str(on_account.get(k, Decimal("0"))),
                         "unallocated_lines_in_fy": str(unallocated.get(k, Decimal("0")))})
    rows.sort(key=lambda r: -abs(Decimal(r["bills_minus_closing"])))
    return {"ledgers_with_difference": len(rows), "sum_difference": str(total),
            "bill_parties_not_in_group": sorted({b["ledger_name"] for b in bills} - {v["name"] for v in bal.values()})[:20],
            "ledgers": rows}


class _Progress:
    """Resumable full-detail state per FY (B7), written after every day."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, fy: str) -> Dict[str, Any]:
        return self.data.get(fy, {})

    def save(self, fy: str, st: Dict[str, Any]) -> None:
        self.data[fy] = st
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data), encoding="utf-8")
        tmp.replace(self.path)


def _header_scan(src: TallyV2Source, fy: FinancialYear, as_of: date) -> List[Dict[str, Any]]:
    """Voucher headers of the FY window, one MONTH-scoped request per month (B6)."""
    rows: List[Dict[str, Any]] = []
    for a, b in month_chunks(fy.start, as_of):
        rows.extend(_header_rows(src._root(tx.voucher_request(tx.MANIFEST_FETCH, date_from=a, date_to=b, scope=src.scope),
                                           "month:headers")))
    return rows


def _touched_ledgers(root: ET.Element, names: set) -> Dict[str, List[str]]:
    """GUID -> the debtor / creditor ledgers (lower-case) each voucher of a day answer posts to."""
    out: Dict[str, List[str]] = {}
    for v in X.voucher_elements(root):
        g = tx.text(v, "GUID")
        if not g:
            continue
        hit = sorted({tx.text(e, "LEDGERNAME").strip().lower() for e in X._entries(v)} & names)
        if hit:
            out[g] = hit
    return out


def changed_during_run(baseline: List[Dict[str, Any]], end: List[Dict[str, Any]], baseline_alter_id: int) -> Dict[str, Dict[str, Any]]:
    """2.2.2 (M2): vouchers created, altered or deleted in Tally between the baseline header scan (taken BEFORE
    any balance or detail read) and the closing header scan. AlterIDs are company-wide and only increase, so any
    voucher created or altered after the baseline has an AlterID above the highest one seen in the baseline."""
    base = {r["guid"]: r for r in baseline if r["guid"]}
    last = {r["guid"]: r for r in end if r["guid"]}
    out: Dict[str, Dict[str, Any]] = {}
    for g, r in last.items():
        if g not in base:
            out[g] = {**r, "change": "created"}
        elif r["alter_id"] > baseline_alter_id:
            out[g] = {**r, "change": "altered"}
    for g, r in base.items():
        if g not in last:
            out[g] = {**r, "change": "deleted or re-dated out of the FY"}
    return out


def _dec_map(d: Dict[str, str]) -> Dict[str, Decimal]:
    return {k: Decimal(v) for k, v in (d or {}).items()}


def _str_map(d: Dict[str, Decimal]) -> Dict[str, str]:
    return {k: str(v) for k, v in d.items()}


def validate_fy(src: TallyV2Source, fy: FinancialYear, company: str, today: date, full: bool,
                progress: Callable[[str], None], prog: Optional[_Progress] = None, live: bool = False) -> Dict[str, Any]:
    t0 = time.time()
    as_of = min(today, fy.end)
    prev = fy.previous
    checks: List[Dict[str, Any]] = []
    out: Dict[str, Any] = {"fy": fy.label, "window": [fy.start.isoformat(), as_of.isoformat()], "checks": checks}

    st = (prog.get(fy.label) if prog else {}) or {}
    if st.get("as_of") != as_of.isoformat():
        st = {}

    # 2.2.2 (M2): BASELINE header scan before any balance or detail read. A resumed run keeps its original
    # baseline, so everything changed since the run first started is recognised.
    src.set_scope(tx.Scope(fy.start, as_of, company))
    if st.get("baseline"):
        rows = st["baseline"]["rows"]
        a0 = int(st["baseline"]["alter_id"])
        progress(f"FY {fy.label}: resuming with the baseline taken at the start of the run (AlterID {a0})")
    else:
        progress(f"FY {fy.label}: baseline voucher headers (before any balance is read), one month-scoped request per month")
        rows = _header_scan(src, fy, as_of)
        a0 = max((r["alter_id"] for r in rows), default=0)
        if prog and full:
            st = {"as_of": as_of.isoformat(), "baseline": {"alter_id": a0, "rows": rows}}
            prog.save(fy.label, st)
    baseline = {"alter_id": a0, "rows": rows}

    src.set_scope(tx.Scope(prev.start, prev.end, company))
    prev_debtors = src.debtor_balances()
    prev_creditors = src.creditors()
    src.set_scope(tx.Scope(fy.start, as_of, company))   # A5: balances to the window end
    progress(f"FY {fy.label}: masters and balances to {as_of}")
    m = src.masters(full_debtors=True)
    debtors = src.debtor_balances()
    creditors = src.creditors()

    for label, group, bal, prev_bal in (("debtors", "Sundry Debtors", debtors, prev_debtors),
                                        ("creditors", "Sundry Creditors", creditors, prev_creditors)):
        s_open = sum((b["opening"] for b in bal.values()), Decimal("0"))
        s_close = sum((b["closing"] for b in bal.values()), Decimal("0"))
        gs_close = src.group_summary_net(group, fy.start, as_of)
        gs_prev = src.group_summary_net(group, prev.start, prev.end)
        nonzero = sum(1 for b in bal.values() if b["opening"] or b["closing"])
        out[label] = {"count": len(bal), "nonzero": nonzero, "sum_opening": str(s_open), "sum_closing": str(s_close),
                      "group_summary_closing": str(gs_close), "group_summary_previous_fy_closing": str(gs_prev)}
        _check(checks, f"{label}: sum closing to {as_of} = Group Summary {as_of} (same date)", abs(s_close - gs_close) <= TOLERANCE,
               f"{s_close} vs {gs_close}")
        _check(checks, f"{label}: sum opening = Group Summary {prev.end}", abs(s_open - gs_prev) <= TOLERANCE,
               f"{s_open} vs {gs_prev}")
        cont = _continuity(bal, prev_bal)
        out[label]["continuity_with_" + prev.label] = cont
        _check(checks, f"{label}: opening {fy.label} = closing {prev.label} per ledger", cont["different"] == 0,
               f"equal={cont['equal']} different={cont['different']}")
        if s_open == s_close and s_close != 0 and nonzero:
            _check(checks, f"{label}: opening differs from closing (untyped-scope symptom)", False,
                   "every sum opening equals sum closing: the balances look like today's balance in both columns")

    guids = [r["guid"] for r in rows if r["guid"]]
    lo, hi = fy.start.isoformat(), as_of.isoformat()
    outside = [r for r in rows if r["date"] and not (lo <= r["date"] <= hi)]
    dups = len(guids) - len(set(guids))
    out["voucher_headers"] = {"count": len(rows), "unique_guids": len(set(guids)), "no_guid": len(rows) - len(guids),
                              "duplicate_guids": dups, "outside_fy": len(outside),
                              "cancelled": sum(r["cancelled"] for r in rows), "optional": sum(r["optional"] for r in rows),
                              "by_type": dict(Counter(r["type"] for r in rows).most_common()),
                              "min_date": min((r["date"] for r in rows if r["date"]), default=None),
                              "max_date": max((r["date"] for r in rows if r["date"]), default=None)}
    _check(checks, "voucher headers: every voucher dated inside the FY", not outside, f"outside={len(outside)}")
    _check(checks, "voucher headers: no duplicate GUID", dups == 0, f"duplicates={dups}")
    _check(checks, "voucher headers: count (informational; 0 is a valid answer only for an empty FY)", None, len(set(guids)))
    out["_guids"] = set(guids)

    debtor_names, creditor_names = set(debtors), set(creditors)
    party_names = debtor_names | creditor_names
    on_account: Dict[str, Decimal] = {}
    unallocated: Dict[str, Decimal] = {}
    touch: Dict[str, List[str]] = dict(st.get("touch") or {})
    good_all: set = set()
    bad_all = 0
    mv_d: Dict[str, Decimal] = {}
    mv_c: Dict[str, Decimal] = {}
    if full:
        good_all = set(st.get("guids", []))
        bad_all = int(st.get("bad", 0))
        mv_d, mv_c = _dec_map(st.get("mv_d")), _dec_map(st.get("mv_c"))
        on_account, unallocated = _dec_map(st.get("on_account")), _dec_map(st.get("unallocated"))
        alloc = Counter(st.get("alloc", {}))
        start = date.fromisoformat(st["next_day"]) if st.get("next_day") else fy.start
        if st.get("next_day"):
            progress(f"FY {fy.label}: resuming full detail at {start}")
        n_days = (as_of - fy.start).days + 1
        for d in _days(start, as_of):
            i = (d - fy.start).days
            if i % 15 == 0:
                progress(f"FY {fy.label}: full detail day {i + 1}/{n_days} ({d})")
            root = src._root(tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=d, scope=src.scope), "day:vouchers")
            good, bad = X.parse_vouchers(root, m)
            good_all.update(v["guid"] for v in good)
            bad_all += len(bad)
            touch.update(_touched_ledgers(root, party_names))
            for k, a in ledger_movements(root, m, debtor_names).items():
                mv_d[k] = mv_d.get(k, Decimal("0")) + a
            for k, a in ledger_movements(root, m, creditor_names).items():
                mv_c[k] = mv_c.get(k, Decimal("0")) + a
            for v in good:
                post = posts_to_ledgers(v)
                for line in v["debtor_lines"]:
                    k = line["ledger_name"].strip().lower()
                    for ba in line["bill_allocations"]:
                        alloc["bill:" + (ba.get("bill_type") or "?")] += 1
                        if post and (ba.get("bill_type") or "").lower() == "on account":
                            on_account[k] = on_account.get(k, Decimal("0")) + Decimal(str(ba.get("amount") or "0"))
                    if post:
                        rest = Decimal(line["amount"]) - sum((Decimal(str(ba.get("amount") or "0")) for ba in line["bill_allocations"]), Decimal("0"))
                        if abs(rest) > TOLERANCE:
                            unallocated[k] = unallocated.get(k, Decimal("0")) + rest
                for line in v["debtor_lines"] + v["counter_lines"]:
                    for bk in line.get("bank_allocations") or []:
                        alloc["bank"] += 1
                        alloc["bank_with_instrument"] += bool(bk.get("instrument_number"))
                        alloc["bank_with_utr"] += bool(bk.get("unique_reference"))
            if prog:
                prog.save(fy.label, {"as_of": as_of.isoformat(), "next_day": (d + timedelta(days=1)).isoformat(),
                                     "guids": sorted(good_all), "bad": bad_all, "mv_d": _str_map(mv_d), "mv_c": _str_map(mv_c),
                                     "on_account": _str_map(on_account), "unallocated": _str_map(unallocated),
                                     "alloc": dict(alloc), "baseline": baseline, "touch": touch})
        out["voucher_full_detail"] = {"parsed": len(good_all), "rejected_by_parser": bad_all,
                                      "same_guid_set_as_headers": good_all == set(guids), "allocations": dict(alloc)}

    progress(f"FY {fy.label}: bills as of {as_of} (typed form)")
    books = getattr(src, "books_from", None)
    for label, req, names, key in (("bills receivable", tx.bills_receivable_request, debtor_names, "bills_receivable"),
                                   ("bills payable", tx.bills_payable_request, creditor_names, "bills_payable")):
        allb = X.parse_bills_any(src._root(req(as_of, company, books), "bills:" + key))
        try:
            check_bill_dates(allb, as_of, label)
            _check(checks, f"{label}: no bill dated after {as_of}", True, f"{len(allb)} bills, latest "
                   f"{max((b['bill_date'] for b in allb if b.get('bill_date')), default=None)}")
        except BillsDateInvalid as ex:
            _check(checks, f"{label}: no bill dated after {as_of}", False, str(ex)[:300])
        party = [b for b in allb if b["ledger_name"].strip().lower() in names]
        s = sum((Decimal(b["pending_amount"]) for b in party), Decimal("0"))
        out[key] = {"as_of": as_of.isoformat(), "all": len(allb), "party_bills": len(party), "party_sum": str(s),
                    "party_bills_with_due_date": sum(1 for b in party if b.get("due_date")),
                    "other_party_bills": len(allb) - len(party)}
        _check(checks, f"{label}: every party bill has a due date", all(b.get("due_date") for b in party),
               f"{out[key]['party_bills_with_due_date']} of {len(party)}")
        if key == "bills_receivable":
            out["bills_vs_balances_debtors"] = bills_vs_balances(party, debtors, on_account, unallocated)
            _check(checks, "bills receivable sum vs sum debtor closing (explained per ledger in bills_vs_balances_debtors)", None,
                   f"{s} vs {out['debtors']['sum_closing']}; difference {s - Decimal(out['debtors']['sum_closing'])}; "
                   f"{out['bills_vs_balances_debtors']['ledgers_with_difference']} ledgers differ")

    # 2.2.2 (M2): CLOSING header scan -> what staff created, altered or deleted while the run was reading.
    progress(f"FY {fy.label}: closing voucher headers (changes made in Tally during this run)")
    end_rows = _header_scan(src, fy, as_of)
    changed = changed_during_run(rows, end_rows, a0)
    numbers: Dict[str, str] = {}
    changed_days = sorted({c["date"] for c in changed.values()
                           if c["date"] and not c["change"].startswith("deleted") and lo <= c["date"] <= hi})
    for ymd in changed_days:   # read each changed date once more: voucher number and CURRENT ledgers of every changed voucher
        root = src._root(tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date.fromisoformat(ymd), scope=src.scope), "day:changed")
        t = _touched_ledgers(root, party_names)
        for v in X.voucher_elements(root):
            g = tx.text(v, "GUID")
            if g in changed:
                touch[g] = sorted(set(touch.get(g, [])) | set(t.get(g, [])))   # before AND after an alteration
                numbers[g] = tx.text(v, "VOUCHERNUMBER")
    unknown = sorted(g for g in changed if g not in touch)
    touched_keys = sorted({k for g in changed for k in touch.get(g, [])})
    display = {**{k: b["name"] for k, b in creditors.items()}, **{k: b["name"] for k, b in debtors.items()}}
    out["changed_during_run"] = {
        "baseline_alter_id": a0, "closing_alter_id": max((r["alter_id"] for r in end_rows), default=0),
        "vouchers": len(changed),
        "by_change": dict(Counter(c["change"] for c in changed.values())),
        "list": [{"guid": g, "change": c["change"], "date": c["date"], "type": c["type"], "number": numbers.get(g) or None,
                  "alter_id": c["alter_id"], "ledgers": [display.get(k, k) for k in touch.get(g, [])]}
                 for g, c in sorted(changed.items(), key=lambda x: (x[1]["date"], x[0]))][:500],
        "ledgers_touched": [display.get(k, k) for k in touched_keys],
        "vouchers_with_unknown_ledgers": unknown[:100],
    }
    _check(checks, "vouchers created / altered / deleted in Tally during this run (excluded from the comparisons below)",
           None, f"{len(changed)} voucher(s), {len(touched_keys)} ledger(s) touched"
                 + (f", {len(unknown)} with unknown ledgers" if unknown else ""))

    if full:
        ch = set(changed)
        base_set = set(guids)
        if good_all == base_set:
            _check(checks, "full detail: same GUID set as the headers", True, f"full={len(good_all)} headers={len(base_set)}")
        elif (good_all - ch) == (base_set - ch):
            _check(checks, "full detail: same GUID set as the headers", True,
                   f"full={len(good_all)} headers={len(base_set)}; every difference is a voucher changed during the run "
                   f"({len((good_all ^ base_set) & ch)}), listed in changed_during_run")
        else:
            _check(checks, "full detail: same GUID set as the headers", False,
                   f"full={len(good_all)} headers={len(base_set)}; {len((good_all ^ base_set) - ch)} difference(s) NOT explained "
                   f"by changes during the run, e.g. {sorted((good_all ^ base_set) - ch)[:5]}")
        _check(checks, "full detail: no voucher rejected by the agent's parser", bad_all == 0, f"rejected={bad_all}")
        excused = set(touched_keys)
        for label, bal, mv in (("debtor", debtors, mv_d), ("creditor", creditors, mv_c)):
            bad_rec = _reconcile(bal, mv)
            real = [b for b in bad_rec if b["ledger"].strip().lower() not in excused]
            out[f"{label}_reconciliation"] = {"ledgers": len(bal), "mismatched": len(bad_rec),
                                              "mismatched_not_explained": len(real),
                                              "excluded_changed_during_run": len(bad_rec) - len(real), "examples": real[:20]}
            judged = len(bal) - (len(bad_rec) - len(real))
            note = (f"; {len(bad_rec) - len(real)} ledger(s) touched by vouchers changed during the run excluded"
                    if len(bad_rec) != len(real) else "")
            if not real:
                _check(checks, f"per {label}: opening + movements = closing", True, f"{judged} of {judged} reconcile{note}")
            elif unknown:
                _check(checks, f"per {label}: opening + movements = closing", None,
                       f"{judged - len(real)} of {judged} reconcile{note}; {len(real)} mismatch(es) cannot be judged: "
                       f"{len(unknown)} voucher(s) changed during the run whose ledgers are unknown (deleted before being read)",
                       status=NOT_VERIFIED)
            else:
                _check(checks, f"per {label}: opening + movements = closing", False, f"{judged - len(real)} of {judged} reconcile{note}")

    if live:
        out["incremental_equivalence"] = incremental_equivalence(src, fy, as_of, company, checks)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def incremental_equivalence(src: TallyV2Source, fy: FinancialYear, as_of: date, company: str,
                            checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """B4: the agent's month-scoped incremental headers = one FY-wide AlterID request (the 2.2.0 form), for a
    seed 50 below the newest AlterID of yesterday/today. Skipped (NOT VERIFIED) when those days are empty."""
    y = max(fy.start, as_of - timedelta(days=1))
    recent = _header_rows(src._root(tx.voucher_request(tx.MANIFEST_FETCH, date_from=y, date_to=as_of, scope=src.scope), "incr:seed"))
    alters = sorted(r["alter_id"] for r in recent if r["alter_id"])
    if not alters:
        _check(checks, "incremental: month-scoped = FY-wide", None, "no voucher yesterday/today: no safe seed", NOT_VERIFIED)
        return {"verified": False}
    seed = alters[-1] - 50
    wide = {g for g, _, _ in X.parse_manifest_entries(src._root(
        tx.voucher_request(tx.MANIFEST_FETCH, date_from=fy.start, date_to=as_of, min_alter_id=seed, scope=src.scope),
        "incr:fy-wide-reference"))}
    month = set()
    for a, b in month_chunks(fy.start, as_of):
        month.update(g for g, _, _ in src.changed_headers(a, b, seed))
    ok = wide == month and len(wide) > 0
    _check(checks, "incremental: month-scoped headers = FY-wide headers (AlterID > seed)", ok,
           f"seed {seed}: FY-wide {len(wide)}, month-scoped {len(month)}")
    return {"verified": True, "seed": seed, "fy_wide": len(wide), "month_scoped": len(month), "identical": wide == month}


def run_validation(fys: List[FinancialYear], out_dir: Path, full: bool = True, client: Optional[TallyClient] = None,
                   today: Callable[[], date] = ist_today, pause: float = 0.5, progress: Callable[[str], None] = print,
                   guard: Optional[TallyGuard] = None, sampler: Optional[ResponsivenessSampler] = None,
                   live_label: Optional[str] = None) -> Dict[str, Any]:
    client = client or TallyClient()
    out_dir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"tool": f"FieldTrack Tally Agent {AGENT_VERSION} validate-fy",
                              "upload_status": "NOT_UPLOADED - read-only validation; nothing was sent to any backend",
                              "started": datetime.now(timezone.utc).isoformat(), "today_ist": today().isoformat(),
                              "full_detail": full, "financial_years": {}}
    if guard is None:
        guard = TallyGuard(out_dir, duty_factor=settings.tally_duty_factor, min_pause=settings.tally_min_pause_seconds,
                           lock_wait=settings.tally_lock_wait_seconds, base_cooldown=settings.tally_cooldown_seconds,
                           max_cooldown=settings.tally_cooldown_max_seconds)
    try:
        company = guard.request("company", client.get_company_info, connection_errors=(TallyConnectionError,))
    except Exception as ex:
        report["result"] = f"REFUSED: Tally not reachable ({type(ex).__name__}: {ex})"
        _write(out_dir, report, guard, sampler)
        return report
    report["company"] = company
    if not company or company.get("error") or not company.get("name"):
        report["result"] = "REFUSED: " + (company.get("error") if company else "no company loaded")
        _write(out_dir, report, guard, sampler)
        return report
    src = TallyV2Source(client, pause, guard=guard, books_from=books_from_of(company))
    prog = _Progress(out_dir / "validate_progress.json")
    guid_sets: Dict[str, set] = {}
    for fy in fys:
        try:
            r = validate_fy(src, fy, company["name"], today(), full, progress, prog, live=fy.label == live_label)
            guid_sets[fy.label] = r.pop("_guids")
        except Exception as ex:  # stops this FY only; progress is kept for --resume
            r = {"fy": fy.label, "error": f"{type(ex).__name__}: {ex}",
                 "checks": [{"check": "validation ran to completion", "status": FAIL, "detail": str(ex)[:300]}]}
            report["financial_years"][fy.label] = r
            if isinstance(ex, (TallyConnectionError,)) or type(ex).__name__ in ("TallyCoolingDown", "TallyBusy"):
                report["stopped"] = f"stopped at FY {fy.label}: {type(ex).__name__} - rerun with --resume {out_dir}"
                break
            continue
        report["financial_years"][fy.label] = r
    labels = list(guid_sets)
    cross = {}
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            cross[f"{labels[i]}x{labels[j]}"] = len(guid_sets[labels[i]] & guid_sets[labels[j]])
    report["cross_fy_duplicate_guids"] = cross
    fails = [f"{k}: {c['check']}" for k, r in report["financial_years"].items() for c in r.get("checks", []) if c["status"] == FAIL]
    if any(cross.values()):
        fails.append(f"GUIDs present in two FYs: {cross}")
    not_verified = [f"{k}: {c['check']}" for k, r in report["financial_years"].items() for c in r.get("checks", [])
                    if c["status"] == NOT_VERIFIED]
    report["failed_checks"] = fails
    report["not_verified"] = not_verified
    complete = len(report["financial_years"]) == len(fys) and "stopped" not in report
    report["result"] = ("ALL CHECKS PASSED" if not fails and complete else
                        f"{len(fails)} CHECK(S) FAILED" if fails else "INCOMPLETE - NOT VERIFIED")
    report["finished"] = datetime.now(timezone.utc).isoformat()
    _write(out_dir, report, guard, sampler)
    return report


def _load_report(out_dir: Path, report: Dict[str, Any], guard: Optional[TallyGuard],
                 sampler: Optional[ResponsivenessSampler]) -> None:
    """AC3 measurements: per-request durations, busy share, Not-Responding stretches."""
    if guard is not None:
        rows = guard.telemetry.rows
        with (out_dir / "tally_requests.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["start_utc", "seconds", "kind", "bytes"])
            for st, sec, kind, size in rows:
                w.writerow([datetime.fromtimestamp(st, timezone.utc).isoformat(), sec, kind, size])
        span = (rows[-1][0] + rows[-1][1] - rows[0][0]) if rows else 0
        busy = sum(r[1] for r in rows)
        report["tally_load"] = {**guard.telemetry.summary(), "span_seconds": round(span, 1),
                                "busy_share_percent": round(100 * busy / span, 1) if span else None,
                                "slowest": [{"kind": k, "seconds": s} for _, s, k, _ in sorted(rows, key=lambda r: -r[1])[:10]]}
    if sampler is not None:
        report["tally_responsiveness"] = sampler.summary()


def _write(out_dir: Path, report: Dict[str, Any], guard: Optional[TallyGuard] = None,
           sampler: Optional[ResponsivenessSampler] = None) -> None:
    _load_report(out_dir, report, guard, sampler)
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    lines = [report["tool"], report["upload_status"], f"company: {report.get('company')}", f"result: {report.get('result')}", ""]
    if report.get("stopped"):
        lines += [f"STOPPED: {report['stopped']}", ""]
    for label, r in report.get("financial_years", {}).items():
        lines.append(f"== FY {label}  window {r.get('window')}  ({r.get('seconds', '?')} s)")
        for c in r.get("checks", []):
            lines.append(f"  [{c['status']}] {c['check']}: {c['detail']}")
        for k in ("debtors", "creditors", "voucher_headers", "voucher_full_detail", "debtor_reconciliation",
                  "creditor_reconciliation", "bills_receivable", "bills_payable", "incremental_equivalence"):
            if k in r:
                v = {kk: vv for kk, vv in r[k].items() if kk not in ("examples", "by_type")} if isinstance(r[k], dict) else r[k]
                lines.append(f"  {k}: {json.dumps(v, default=str)}")
        bv = r.get("bills_vs_balances_debtors")
        if bv:
            lines.append(f"  bills vs balances (debtors): {bv['ledgers_with_difference']} ledgers differ, sum {bv['sum_difference']}")
        cd = r.get("changed_during_run")
        if cd:
            lines.append(f"  changed in Tally during this run: {cd['vouchers']} voucher(s) {cd['by_change']} "
                         f"(AlterID {cd['baseline_alter_id']} -> {cd['closing_alter_id']})")
            for c in cd["list"][:50]:
                lines.append(f"    {c['change']}: {c['date']} {c['type']} {c['number'] or ''} GUID {c['guid']} "
                             f"ledgers {', '.join(c['ledgers']) or '(unknown)'}")
            if len(cd["list"]) > 50:
                lines.append(f"    ... {len(cd['list']) - 50} more in validation_report.json")
        lines.append("")
    lines.append(f"cross-FY duplicate GUIDs: {report.get('cross_fy_duplicate_guids')}")
    if "tally_load" in report:
        tl = report["tally_load"]
        lines.append(f"Tally load: {tl['requests']} requests, max {tl['max_seconds']} s ({tl['max_kind']}), over 15 s: "
                     f"{tl['over_15s']}, failures {tl['failures']}, busy share {tl['busy_share_percent']}% of {tl['span_seconds']} s")
    if "tally_responsiveness" in report:
        tr = report["tally_responsiveness"]
        lines.append(f"Tally responsiveness: {'measured' if tr['verified'] else 'NOT VERIFIED'}; samples {tr['samples']}; "
                     f"Not-Responding stretches {tr['not_responding_stretches']}, longest {tr['longest_not_responding_seconds']} s")
    (out_dir / "validation_summary.txt").write_text("\n".join(lines), encoding="utf-8")

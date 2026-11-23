"""H2 independent checker. Reads Tally DIRECTLY (port 9000, its own Export requests, NOT through the adapter and NOT with
the agent's code), then:

  A. Tally completeness: the FY-wide read (1 Apr 2026 - 31 Mar 2027) and the day-by-day read of every allowed day
     (1st, 2nd, 31st) give the same vouchers (GUID, AlterID, date, cancelled), and equal the driver's voucher ledger
     (pre-existing + created - deleted).
  B. Tally's own totals: each debtor's ClosingBalance = OpeningBalance + its posted movements recomputed from the
     vouchers; the Sundry Debtors Group Summary = the sum; Tally's Bills Receivable = the open bills recomputed from
     the vouchers' bill allocations.
  C. FieldTrack vs Tally (replay oracle): vouchers / AlterIDs, rows (type, ledger, signed amount, date), receipt links
     and amounts, outstanding per ledger, duplicates, links to retired invoices.

    python h2_check.py [label] [--no-fieldtrack]   -> one JSON line appended to results/checks.jsonl, printed summary
Exit 0 if A and B pass (and C is equal, unless --no-fieldtrack); exit 1 otherwise.

All results: real TallyPrime (Educational Mode); the agent reads it through a test-only date adapter.
"""
from __future__ import annotations

import asyncio
import json
import pickle
import re
import sys
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "harness"))
sys.path.insert(0, str(HERE.parents[2]))              # repo root (replay oracle imports the released agent package)
import h2_safety as hs  # noqa: E402
import h2_tally as t  # noqa: E402

FY0, FY1 = date(2026, 4, 1), date(2027, 3, 31)
LIVE_START = FY0
PRE_EXISTING: set = set()        # all H2 vouchers are in the driver's voucher ledger (backfilled for the smoke ones)
CENT = Decimal("0.01")
NON_ACCOUNTING = {"sales order", "purchase order", "delivery note", "receipt note", "rejections in", "rejections out",
                  "stock journal", "physical stock", "memorandum", "reversing journal", "job work in order",
                  "job work out order", "material in", "material out"}


def money(s) -> Decimal:
    s = (s or "").strip()
    return Decimal(s) if s else Decimal("0")


def allowed_days(a: date, b: date):
    d = a
    while d <= b:
        if d.day in (1, 2, 31):
            yield d
        d += timedelta(days=1)


def snapshot(vmap):
    return {g: (v["alter"], v["date"], v["cancelled"]) for g, v in vmap.items()}


# ------------------------------------------------------------------ A. completeness
def check_completeness():
    fy = t.voucher_map(FY0, FY1)
    days = {}
    for d in allowed_days(FY0, FY1):
        days.update(t.voucher_map(d, d))
    a, b = snapshot(fy), snapshot(days)
    expected = t.expected_guids_from_ledger(PRE_EXISTING)
    res = {"fy_read": len(a), "day_by_day_read": len(b), "driver_ledger_expected": len(expected),
           "fy_vs_days_equal": a == b, "tally_vs_driver_ledger_equal": set(a) == expected,
           "only_fy": sorted(set(a) - set(b))[:5], "only_days": sorted(set(b) - set(a))[:5],
           "missing_vs_ledger": sorted(expected - set(a))[:5], "unexpected_vs_ledger": sorted(set(a) - expected)[:5]}
    res["PASS"] = res["fy_vs_days_equal"] and res["tally_vs_driver_ledger_equal"]
    return fy, res


# ------------------------------------------------------------------ B. Tally's own totals
def _vtype_parents(raw: str) -> dict:
    parent = {}
    for vt in t._root(raw).iter("VOUCHERTYPE"):
        n = (vt.attrib.get("NAME") or "").strip()
        if n:
            parent[n] = (vt.findtext("PARENT") or "").strip()
    out = {}
    for n in parent:
        cur, hops = n, 0
        while parent.get(cur) and parent[cur] != cur and hops < 20:
            cur, hops = parent[cur], hops + 1
        out[n] = cur
    return out


def _report(report: str, to: date) -> ET.Element:
    hs.assert_test_company()
    xml = (f"<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Data</TYPE><ID>{report}</ID>"
           f"</HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
           f'<SVFROMDATE TYPE="Date">{t.tday(FY0)}</SVFROMDATE><SVTODATE TYPE="Date">{t.tday(to)}</SVTODATE>'
           f"{'<GROUPNAME>Sundry Debtors</GROUPNAME>' if report == 'Group Summary' else ''}"
           f"<SVCURRENTCOMPANY>{hs.LOCK['company_name']}</SVCURRENTCOMPANY></STATICVARIABLES></DESC></BODY></ENVELOPE>")
    return t._root(t._post(xml, timeout=300))


def check_totals(fy, deb_raw, vt_raw, today: date):
    asof = max(d for d in allowed_days(FY0, today))       # Educational Mode: the last allowed day <= today
    parents = _vtype_parents(vt_raw)
    debtors = {}
    for led in t._root(deb_raw).iter("LEDGER"):
        n = (led.attrib.get("NAME") or "").strip()
        if n:
            debtors[n.lower()] = {"name": n, "opening": money(led.findtext("OPENINGBALANCE")),
                                  "closing": money(led.findtext("CLOSINGBALANCE")),
                                  "opening_bills": [((b.findtext("NAME") or "").strip(), money(b.findtext("OPENINGBALANCE")))
                                                    for b in led.iter("BILLALLOCATIONS.LIST")
                                                    if (b.findtext("NAME") or "").strip()]}
    mv = defaultdict(Decimal)
    bills = defaultdict(Decimal)                             # (ledger lower, bill name) -> Tally-signed amount
    for n, d in debtors.items():                             # opening bills held in the ledger masters
        for bname, amt in d["opening_bills"]:
            bills[(n, bname)] += amt
    for v in fy.values():
        if v["date"] > asof.isoformat():
            continue                                         # post-dated: outside the as-of balances
        e = v["elem"]
        parent = parents.get(v["vtype"], v["vtype"]).lower()
        if v["cancelled"] or (e.findtext("ISOPTIONAL") or "").strip().lower() == "yes" or parent in NON_ACCOUNTING:
            continue
        for le in e.iter("ALLLEDGERENTRIES.LIST"):
            n = (le.findtext("LEDGERNAME") or "").strip().lower()
            if n in debtors:
                mv[n] += money(le.findtext("AMOUNT"))
                for b in le.iter("BILLALLOCATIONS.LIST"):
                    if (b.findtext("BILLTYPE") or "").strip().lower() != "on account" and (b.findtext("NAME") or "").strip():
                        bills[(n, b.findtext("NAME").strip())] += money(b.findtext("AMOUNT"))
    ledgers_bad = []
    for n, d in debtors.items():
        rec = d["opening"] + mv[n]
        if abs(rec - d["closing"]) > CENT:
            ledgers_bad.append({"ledger": d["name"], "tally_closing": str(d["closing"]), "recomputed": str(rec)})
    sum_closing = sum((d["closing"] for d in debtors.values()), Decimal("0"))
    gs = _report("Group Summary", asof)
    gs_amounts = [money(x.text) for x in gs.iter() if x.tag in ("DSPCLDRAMTA", "DSPCLCRAMTA") and (x.text or "").strip()]
    gs_total = sum(gs_amounts, Decimal("0"))
    br = _report("Bills Receivable", asof)
    tally_bills, cur = {}, None
    for ch in list(br):
        if ch.tag == "BILLFIXED":
            cur = ((ch.findtext("BILLPARTY") or "").strip().lower(), (ch.findtext("BILLREF") or "").strip())
        elif ch.tag == "BILLCL" and cur:
            tally_bills[cur] = money(ch.text)
    # Tally lists DEBIT-balance bills under Bills Receivable and CREDIT-balance bills (e.g. a receipt still allocated to a
    # cancelled / deleted invoice) under Bills Payable: compare each side with its own report.
    bp = _report("Bills Payable", asof)
    tally_credit, cur = {}, None
    for ch in list(bp):
        if ch.tag == "BILLFIXED":
            cur = ((ch.findtext("BILLPARTY") or "").strip().lower(), (ch.findtext("BILLREF") or "").strip())
        elif ch.tag == "BILLCL" and cur:
            if cur[0] in debtors:                            # only debtor ledgers' credit bills
                tally_credit[cur] = money(ch.text)
    open_recomputed = {k: a for k, a in bills.items() if a < 0}
    credit_recomputed = {k: a for k, a in bills.items() if a > 0}

    def diff(tally_side, rec_side):
        return [{"bill": list(k), "tally": str(tally_side.get(k)), "recomputed": str(rec_side.get(k))}
                for k in set(tally_side) | set(rec_side)
                if abs(tally_side.get(k, Decimal("0")) - rec_side.get(k, Decimal("0"))) > CENT]
    bills_bad = diff(tally_bills, open_recomputed)
    credit_bad = diff(tally_credit, credit_recomputed)
    res = {"as_of": str(asof), "debtor_ledgers": len(debtors), "ledgers_closing_mismatch": ledgers_bad[:10],
           "sum_debtor_closing": str(sum_closing), "group_summary_total": str(gs_total),
           "group_summary_equal": abs(gs_total - sum_closing) <= CENT if gs_amounts else (sum_closing == 0),
           "tally_open_bills": len(tally_bills), "recomputed_open_bills": len(open_recomputed), "bills_mismatch": bills_bad[:10],
           "tally_open_bills_total": str(sum(tally_bills.values(), Decimal("0"))),
           "tally_credit_bills_debtors": len(tally_credit), "recomputed_credit_bills": len(credit_recomputed),
           "credit_bills_mismatch": credit_bad[:10]}
    bills_bad = bills_bad + credit_bad
    res["PASS"] = not ledgers_bad and res["group_summary_equal"] and not bills_bad
    return res


# ------------------------------------------------------------------ C. FieldTrack vs Tally (replay oracle)
def check_fieldtrack(fy, deb_raw, vt_raw, today: date):
    import replay_tally
    import oracle
    import setup_backend as sb
    replay_tally.ALTER_SCALE = 1
    sb.HARNESS_DB = hs.LOCK["backend_db"]
    vouchers = [{"guid": g, "date": v["date"], "alter": v["alter"], "vtype": v["vtype"],
                 "xml": ET.tostring(v["elem"], encoding="unicode")} for g, v in fy.items()]
    vouchers.sort(key=lambda r: (r["alter"], r["guid"]))
    store = Path(tempfile.mkdtemp()) / "store.pkl"
    store.write_bytes(pickle.dumps({"vouchers": vouchers, "masters": {"FtpVchTypes": vt_raw, "FtpDebtors": deb_raw}}))
    tally = replay_tally.ReplayTally(str(store), company_guid=hs.LOCK["company_guid"])
    # ReplayTally SIMULATES entry times (date order assigned by AlterID position) for the recorded replay. Here every
    # voucher was read from the real Tally, so it exists now: visibility must depend only on its own date (else, once a
    # post-dated voucher exists, the newest voucher inherits that future "entry" time and is wrongly hidden).
    for rec in tally.recs.values():
        rec.entered_at = datetime(rec.date.year, rec.date.month, rec.date.day, tzinfo=replay_tally.IST)
    tally.now = datetime(today.year, today.month, today.day, 23, 59, tzinfo=replay_tally.IST)
    ex = oracle.expected(tally, today, LIVE_START, [])

    async def ft():
        import asyncpg
        url = sb.harness_env()["DATABASE_URL"]
        hs.assert_backend_target(url, hs.LOCK["backend_url"])
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            return await oracle.fieldtrack(conn)
        finally:
            await conn.close()
    cmp = oracle.compare(ex, asyncio.run(ft()), LIVE_START)
    return {"summary": cmp["summary"], "samples": cmp["samples"]}


def main(label: str, with_ft: bool = True):
    hs.assert_test_company()
    today = date.today()
    fy, comp = check_completeness()
    asof = max(d for d in allowed_days(FY0, today))
    deb_raw, vt_raw = t.read_debtors_raw(asof), t.read_vtypes_raw()
    tot = check_totals(fy, deb_raw, vt_raw, today)
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "label": label, "today": str(today),
           "A_completeness": comp, "B_tally_totals": tot,
           "labelled": "real TallyPrime (Educational Mode); agent reads through a test-only date adapter"}
    ok = comp["PASS"] and tot["PASS"]
    if with_ft:
        rec["C_fieldtrack"] = check_fieldtrack(fy, deb_raw, vt_raw, today)
        rec["C_equal"] = rec["C_fieldtrack"]["summary"]["equal"]
        ok = ok and rec["C_equal"]
    rec["PASS"] = ok
    (HERE / "results").mkdir(exist_ok=True)
    with (HERE / "results" / "checks.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps(rec, indent=1, default=str)[:6000])
    return ok


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(0 if main(args[0] if args else "manual", "--no-fieldtrack" not in sys.argv) else 1)

"""READ-ONLY feasibility probe: can Educational-Mode Tally give the agent the same answers as a licensed Tally?

Hypothesis (Approach 2): in Educational Mode no voucher can exist on a day other than the 1st, 2nd or 31st. Therefore,
for ANY data in the company, a period [from, to] is equivalent to [next allowed day >= from, last allowed day <= to].
Rewriting ONLY <SVFROMDATE>/<SVTODATE> of an Export request this way, and leaving the agent's exact $Date filters
untouched, should give exactly the licensed-Tally answer.

The probe builds the agent's OWN requests (released source, tally_xml builders) for every request kind it sends, posts
each one twice (as is / remapped) and compares with ground truth read independently. Export only; lock-checked.

    python edu_window_probe.py   -> results/edu_window_probe.json
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[3]))          # repo root, for tally_sync_agent (released source)
import h2_safety as hs  # noqa: E402
import h2_tally as t  # noqa: E402
from tally_sync_agent.extractors import tally_xml as tx  # noqa: E402

EDU = (1, 2, 31)
MON = {m: i + 1 for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}


def allowed(d: date) -> bool:
    return d.day in EDU


def next_allowed(d: date) -> date:
    while not allowed(d):
        d += timedelta(days=1)
    return d


def prev_allowed(d: date) -> date:
    while not allowed(d):
        d -= timedelta(days=1)
    return d


def _parse_tday(s: str) -> date:
    dd, mm, yy = s.split("-")
    return date(int(yy), MON[mm[:3].title()], int(dd))


def remap(xml: str) -> tuple:
    """-> (new xml, (from, to) before, (from, to) after). Only SVFROMDATE / SVTODATE change."""
    f = re.search(r'<SVFROMDATE TYPE="Date">([^<]+)</SVFROMDATE>', xml)
    to = re.search(r'<SVTODATE TYPE="Date">([^<]+)</SVTODATE>', xml)
    if not (f and to):
        return xml, None, None
    a, b = _parse_tday(f.group(1)), _parse_tday(to.group(1))
    na, nb = next_allowed(a), prev_allowed(b)
    if na > nb:                      # no allowed day in the period: no voucher can exist there; leave it as is
        return xml, (a, b), (a, b)
    out = xml.replace(f.group(0), f'<SVFROMDATE TYPE="Date">{tx.tally_day(na)}</SVFROMDATE>', 1)
    out = out.replace(to.group(0), f'<SVTODATE TYPE="Date">{tx.tally_day(nb)}</SVTODATE>', 1)
    return remap_formulae(out), (a, b), (na, nb)


def remap_formulae(xml: str) -> str:
    """$Date >= $$Date:"X" -> next allowed >= X;  $Date <= $$Date:"X" -> last allowed <= X  (equivalent when vouchers can
    only exist on allowed days). $Date = $$Date:"X" is left as is."""
    def ge(m):
        return f'{m.group(1)}$$Date:"{tx.tally_day(next_allowed(_parse_tday(m.group(2))))}"'

    def le(m):
        return f'{m.group(1)}$$Date:"{tx.tally_day(prev_allowed(_parse_tday(m.group(2))))}"'
    xml = re.sub(r'(\$Date &gt;= )\$\$Date:"([^"]+)"', ge, xml)
    xml = re.sub(r'(\$Date &lt;= )\$\$Date:"([^"]+)"', le, xml)
    return xml


def post(xml: str) -> ET.Element:
    hs.assert_test_company()
    assert "<TALLYREQUEST>Export" in xml and "Import" not in xml
    return t._root(t._post(xml, timeout=300))


def count(root, tag):
    return len([e for e in root.iter(tag) if len(e)])


def main():
    hs.assert_test_company()
    C = hs.LOCK["company_name"]
    today, fy0, fy1 = date(2026, 11, 22), date(2026, 4, 1), date(2027, 3, 31)
    truth = t.voucher_map(fy0, fy1)                         # independent reader, FY-wide (allowed end day)
    truth_dates = sorted(v["date"] for v in truth.values())
    res = {"ground_truth": {"vouchers": len(truth), "dates": truth_dates}, "cases": []}
    sc_today = tx.Scope(fy0, today, C)
    reqs = {
        "fast path: changed headers FY start..today, AlterID>0": tx.voucher_request(tx.MANIFEST_FETCH, date_from=fy0, date_to=today, min_alter_id=1, scope=sc_today),
        "hourly window today-31..today (headers)": tx.voucher_request(tx.MANIFEST_FETCH, date_from=today - timedelta(days=31), date_to=today, scope=sc_today),
        "nightly month May 1-31 (headers)": tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), scope=sc_today),
        "nightly month Apr 1-30 (headers)": tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 4, 1), date_to=date(2026, 4, 30), scope=sc_today),
        "nightly month Nov 1-22 (headers)": tx.voucher_request(tx.MANIFEST_FETCH, date_from=date(2026, 11, 1), date_to=today, scope=sc_today),
        "manifest FY start..today (headers)": tx.voucher_request(tx.MANIFEST_FETCH, date_from=fy0, date_to=today, scope=sc_today),
        "first load: single day 1 May (full)": tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date(2026, 5, 1), scope=sc_today),
        "first load: single day 15 May (full)": tx.voucher_request(tx.VOUCHER_FULL_FETCH, day=date(2026, 5, 15), scope=sc_today),
        "repair: range 1 May-2 May (full)": tx.voucher_request(tx.VOUCHER_FULL_FETCH, date_from=date(2026, 5, 1), date_to=date(2026, 5, 2), scope=sc_today),
        "debtor masters (scope FY..today)": tx.debtors_request(scope=sc_today),
        "bills receivable as of today": tx.bills_receivable_request(today, C, fy0),
        "group summary Sundry Debtors FY..today": tx.group_summary_request("Sundry Debtors", fy0, today, C),
    }
    for name, xml in reqs.items():
        new, before, after = remap(xml)
        r0, r1 = post(xml), post(new)
        tag = "LEDGER" if "debtor" in name else ("VOUCHER" if "headers" in name or "full" in name else None)
        case = {"request": name, "period_sent": [str(x) for x in before] if before else None,
                "period_remapped": [str(x) for x in after] if after else None}
        if tag:
            case["as_is"], case["remapped"] = count(r0, tag), count(r1, tag)
        else:  # reports: compare the raw answers' size and key figures
            s0, s1 = ET.tostring(r0, encoding="unicode"), ET.tostring(r1, encoding="unicode")
            case["as_is_bytes"], case["remapped_bytes"] = len(s0), len(s1)
            case["as_is_amounts"] = re.findall(r">(-?\d+\.\d\d)<", s0)[:8]
            case["remapped_amounts"] = re.findall(r">(-?\d+\.\d\d)<", s1)[:8]
            case["remapped_bills"] = re.findall(r"<BILLFIXED>.*?</BILLFIXED>", s1, re.S)[:3]
        res["cases"].append(case)
        print(json.dumps(case, default=str))
    # expected per case (from ground truth: 1 voucher on 2026-05-01)
    out = HERE.parent / "results" / "edu_window_probe.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print("ground truth:", res["ground_truth"])


if __name__ == "__main__":
    main()
